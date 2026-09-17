#!/usr/bin/env python3
"""Portable mounted-bundle verifier for OpenSWE delivery folders."""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import shlex
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any


HEREDOC_PLACEHOLDER = "[CONTENT OF TEST PATCH]"
CONTAINER_CONDA_ROOT = "/data/lwj/test/swe/python_conda_batch"
VALIDATION_CANDIDATE_STATUSES = {"accepted", "accepted_dynamic_verifier", "pending_validation"}
REJECTED_QUALITY_STATUSES = {"unknown_non_static", "rejected", "quality_rejected"}
STATIC_ORACLE_RE = re.compile(
    r"gold_patch_static_discriminator|source_marker_oracle|static source[- ]content oracle|"
    r"oracle_static_|oracle_source_check_|ORACLE_STATIC_FAIL|openswe_oracle_test\.py|"
    r"expected_added|expected_removed|missing marker",
    re.IGNORECASE,
)
STATIC_ASSERTION_TERM_RE = re.compile(
    r"(?:^|_)(?:gold(?:_patch)?|source(?:_text|_code|_content)?|marker|"
    r"expected_added|expected_removed|file_content|oracle_static)(?:_|$)",
    re.IGNORECASE,
)
SOURCE_FILE_RE = re.compile(
    r"(?:^|/)(?!tests?(?:/|$)).+\.(?:py|pyi|pyx)$",
    re.IGNORECASE,
)
TEST_PATH_RE = re.compile(
    r"(^|/)(?:tests?|testing)(?:/|$)|(^|/)(?:test|repro|regression)[^/]*\.py$|"
    r"(?:_test|_spec)\.py$",
    re.IGNORECASE,
)
PATCH_ERROR_RE = re.compile(
    r"OPENSWE_(?:TEST_|GOLD_)?PATCH_APPLY_RC=(-?[1-9]\d*)|"
    r"(?:error:\s*)?patch (?:failed|does not apply)|git apply.*(?:failed|error)",
    re.IGNORECASE,
)
COLLECTION_ERROR_RE = re.compile(
    r"collected\s+0\s+items?|no tests ran|ERROR collecting|not found:\s|"
    r"found no collectors|ImportError while importing test module",
    re.IGNORECASE,
)
ENVIRONMENT_ERROR_RE = re.compile(
    r"ModuleNotFoundError|No module named|cannot import name|ImportError:|"
    r"solver .* not installed|command not found|missing prepared conda env|"
    r"conda not available|undefined symbol|required version",
    re.IGNORECASE,
)
INFRA_ERROR_RE = re.compile(
    r"OPENSWE_INFRA_FAILURE(?:=|:)|Cannot connect to the Docker daemon|docker: Error response|pull access denied|"
    r"Unable to find image|invalid mount config|mount denied|no space left on device|"
    r"permission denied|operation not permitted|OCI runtime|container .* is not running",
    re.IGNORECASE,
)


class GeneratorContractError(ValueError):
    """The bundle eval scripts cannot provide strict command or patch proof."""


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", value).strip("_") or "unknown"


def docker_tag(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-_.").lower()
    return cleaned[:120] or "unknown"


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_patch_file_text(patch_text: str) -> str:
    value = str(patch_text or "")
    if not value or value.endswith("\n"):
        return value
    if value.endswith("\r"):
        return value + "\n"
    return value + "\n"


def combine_patch_text(*patches: str) -> str:
    return "".join(normalize_patch_file_text(patch) for patch in patches if str(patch or "").strip())


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def render_eval_script(eval_skeleton: str, patch_text: str) -> str:
    patch_text = normalize_patch_file_text(patch_text)
    if HEREDOC_PLACEHOLDER in eval_skeleton:
        embedded_patch = patch_text[:-1] if patch_text.endswith("\n") else patch_text
        return eval_skeleton.replace(HEREDOC_PLACEHOLDER, embedded_patch, 1) + "\n"
    pattern = re.compile(r"(git\s+apply[^\n]*<<'?([A-Za-z0-9_]+)'?\n)([\s\S]*?\n)(\2)", re.M)
    match = pattern.search(eval_skeleton)
    if not match:
        raise GeneratorContractError("legacy eval skeleton does not contain a patch heredoc")
    return eval_skeleton[: match.start()] + match.group(1) + patch_text + match.group(4) + eval_skeleton[match.end() :]


def instrument_test_command(eval_script: str, *, inject_missing: bool = True) -> tuple[str, str, str]:
    lines = eval_script.splitlines(keepends=True)
    rc_indexes = [index for index, line in enumerate(lines) if re.fullmatch(r"\s*rc=\$\?\s*", line)]
    if not rc_indexes:
        raise GeneratorContractError("eval script does not expose the selected test command return code")
    rc_index = rc_indexes[-1]
    command_end = rc_index - 1
    while command_end >= 0 and not lines[command_end].strip():
        command_end -= 1
    if command_end < 0:
        raise GeneratorContractError("eval script has no command before rc=$?")
    command_start = command_end
    while command_start > 0 and lines[command_start - 1].rstrip().endswith("\\"):
        command_start -= 1
    command = "".join(lines[command_start : command_end + 1]).strip()
    if not command or "OPENSWE_" in command or command.startswith("echo "):
        raise GeneratorContractError("cannot identify a strict test command in eval script")
    command_sha256 = sha256_text(command)
    proof_hashes = re.findall(r"OPENSWE_TEST_COMMAND_SHA256=([0-9a-fA-F]{64})", eval_script)
    has_started = "OPENSWE_TEST_STARTED=1" in eval_script
    has_finished = "OPENSWE_TEST_FINISHED=1" in eval_script
    has_any_proof = bool(proof_hashes) or has_started or has_finished
    if proof_hashes and has_started and has_finished:
        if any(value.lower() != command_sha256 for value in proof_hashes):
            raise GeneratorContractError("eval command proof hash does not match the selected test command")
        return eval_script, command, command_sha256
    if has_any_proof:
        raise GeneratorContractError("eval script contains incomplete command proof markers")
    if not inject_missing:
        raise GeneratorContractError("eval script is missing strict command proof markers")
    prefix = [
        f'echo "OPENSWE_TEST_COMMAND_SHA256={command_sha256}"\n',
        'echo "OPENSWE_TEST_STARTED=1"\n',
    ]
    lines[command_start:command_start] = prefix
    rc_index += len(prefix)
    lines.insert(rc_index + 1, 'echo "OPENSWE_TEST_FINISHED=1"\n')
    return "".join(lines), command, command_sha256


def uses_bundle_patch_contract(eval_script: str) -> bool:
    return "apply_bundle_patch" in eval_script or bool(
        re.search(r"(?:\$BUNDLE_ROOT|/bundle)/(?:gold|test)_patch\.diff", eval_script)
    )


def validate_bundle_patch_contract(eval_script: str, mode: str) -> None:
    if mode not in {"testonly", "gold"}:
        raise GeneratorContractError(f"unsupported bundle patch mode: {mode}")
    if HEREDOC_PLACEHOLDER in eval_script or re.search(r"git\s+apply[^\n]*<<", eval_script):
        raise GeneratorContractError("bundle patch eval mixes external diff and heredoc patch semantics")
    if "apply_bundle_patch" not in eval_script or not re.search(r"\bcp\b", eval_script):
        raise GeneratorContractError("bundle patch eval must copy patches through apply_bundle_patch")
    if not re.search(r"(?:BUNDLE_ROOT\s*=\s*/bundle|/bundle/(?:gold|test)_patch\.diff)", eval_script):
        raise GeneratorContractError("mounted bundle patch eval does not source diffs from /bundle")
    has_test_patch = "test_patch.diff" in eval_script
    has_gold_patch = "gold_patch.diff" in eval_script
    if not has_test_patch:
        raise GeneratorContractError(f"{mode} eval does not apply test_patch.diff")
    if mode == "testonly" and has_gold_patch:
        raise GeneratorContractError("testonly eval must not apply gold_patch.diff")
    if mode == "gold" and not has_gold_patch:
        raise GeneratorContractError("gold eval does not apply gold_patch.diff")


def validate_existing_command_proof(bundle_dir: Path, expected_sha256: str) -> dict[str, Any]:
    proof: dict[str, Any] = {}
    commands: list[str] = []
    hashes: list[str] = []
    for mode, name in (
        ("testonly", "eval_testonly_mounted.sh"),
        ("gold", "eval_gold_mounted.sh"),
    ):
        script = (bundle_dir / name).read_text(encoding="utf-8")
        if uses_bundle_patch_contract(script):
            validate_bundle_patch_contract(script, mode)
        _, command, command_sha256 = instrument_test_command(script, inject_missing=False)
        commands.append(command)
        hashes.append(command_sha256)
        proof[mode] = {"command": command, "command_sha256": command_sha256, "markers_valid": True}
    if commands[0] != commands[1] or hashes[0] != hashes[1]:
        raise GeneratorContractError("testonly and gold do not use the same selected test command")
    if not expected_sha256 or expected_sha256.lower() != hashes[0]:
        raise GeneratorContractError("task strict_eval_command_sha256 does not match eval command proof")
    return proof


def mounted_eval_script(eval_script: str) -> str:
    return (
        eval_script.replace("/testbed", "/work/testbed")
        .replace(
            "conda not available; mount /root/miniconda3 into the container",
            "conda not available in the base image",
        )
    )


def mounted_runner_text() -> str:
    return """#!/usr/bin/env bash
set +e
MODE="${1:-${OPENSWE_MODE:-testonly}}"
WORK_ROOT="${OPENSWE_WORK_ROOT:-/work}"
TESTBED="${OPENSWE_TESTBED:-/work/testbed}"
rm -rf "$TESTBED"
mkdir -p "$TESTBED"
cp -a /bundle/repo/. "$TESTBED"/
case "$MODE" in
  testonly)
    bash /bundle/eval_testonly_mounted.sh
    ;;
  gold)
    bash /bundle/eval_gold_mounted.sh
    ;;
  user)
    if [ ! -f "$WORK_ROOT/user_eval.sh" ]; then
      echo "missing mounted user eval script: $WORK_ROOT/user_eval.sh"
      echo "OPENSWE_EXIT_CODE=127"
      exit 0
    fi
    bash "$WORK_ROOT/user_eval.sh"
    ;;
  *)
    echo "unknown mounted eval mode: $MODE"
    echo "OPENSWE_EXIT_CODE=2"
    exit 0
    ;;
esac
"""


def regenerate_mounted_scripts(bundle_dir: Path) -> dict[str, Any]:
    task = read_json(bundle_dir / "task.json")
    task["patch"] = normalize_patch_file_text(str(task.get("patch") or ""))
    task["test_patch"] = normalize_patch_file_text(str(task.get("test_patch") or ""))
    (bundle_dir / "gold_patch.diff").write_text(task["patch"], encoding="utf-8")
    (bundle_dir / "test_patch.diff").write_text(task["test_patch"], encoding="utf-8")

    testonly_path = bundle_dir / "eval_testonly_mounted.sh"
    gold_path = bundle_dir / "eval_gold_mounted.sh"
    existing_testonly = testonly_path.read_text(encoding="utf-8") if testonly_path.is_file() else ""
    existing_gold = gold_path.read_text(encoding="utf-8") if gold_path.is_file() else ""
    has_external_contract = uses_bundle_patch_contract(existing_testonly) or uses_bundle_patch_contract(existing_gold)
    if has_external_contract:
        if not uses_bundle_patch_contract(existing_testonly) or not uses_bundle_patch_contract(existing_gold):
            raise GeneratorContractError("testonly and gold must both use the external bundle patch contract")
        validate_bundle_patch_contract(existing_testonly, "testonly")
        validate_bundle_patch_contract(existing_gold, "gold")
        testonly_script, test_command, test_command_sha256 = instrument_test_command(existing_testonly)
        gold_script, gold_command, gold_command_sha256 = instrument_test_command(existing_gold)
    else:
        eval_skeleton = (bundle_dir / "eval_skeleton.sh").read_text(encoding="utf-8")
        mounted_skeleton = mounted_eval_script(eval_skeleton)
        testonly_script, test_command, test_command_sha256 = instrument_test_command(
            render_eval_script(mounted_skeleton, str(task.get("test_patch") or ""))
        )
        gold_script, gold_command, gold_command_sha256 = instrument_test_command(
            render_eval_script(
                mounted_skeleton,
                combine_patch_text(str(task.get("patch") or ""), str(task.get("test_patch") or "")),
            )
        )
    if test_command != gold_command or test_command_sha256 != gold_command_sha256:
        raise GeneratorContractError("testonly and gold do not use the same selected test command")
    task["strict_eval_command"] = test_command
    task["strict_eval_command_sha256"] = test_command_sha256
    write_json(bundle_dir / "task.json", task)
    testonly_path.write_text(
        testonly_script,
        encoding="utf-8",
    )
    gold_path.write_text(
        gold_script,
        encoding="utf-8",
    )
    (bundle_dir / "run_mounted_eval.sh").write_text(mounted_runner_text(), encoding="utf-8")
    return task


def extract_openswe_exit_code(output: str) -> int | None:
    matches = re.findall(r"OPENSWE_EXIT_CODE=(-?\d+)", output)
    return int(matches[-1]) if matches else None


def extract_last_marker(output: str, name: str) -> str | None:
    matches = re.findall(rf"^{re.escape(name)}=(.*)$", output, flags=re.MULTILINE)
    return matches[-1].strip() if matches else None


def added_python_regions(patch_text: str) -> list[dict[str, str]]:
    """Return contiguous added-code regions from Python unified-diff hunks."""
    regions: list[dict[str, str]] = []
    current_path: str | None = None
    in_hunk = False
    added_lines: list[str] = []

    def flush() -> None:
        nonlocal added_lines
        if current_path and added_lines:
            source = "\n".join(added_lines)
            if source.strip():
                regions.append({"path": current_path, "source": source})
        added_lines = []

    for line in patch_text.splitlines():
        if line.startswith("diff --git ") or line.startswith("--- "):
            flush()
            in_hunk = False
            if line.startswith("diff --git "):
                current_path = None
            continue
        if line.startswith("+++ "):
            flush()
            in_hunk = False
            raw_path = line[4:].split("\t", 1)[0].strip()
            if raw_path.startswith("b/"):
                raw_path = raw_path[2:]
            current_path = raw_path if raw_path != "/dev/null" and raw_path.lower().endswith(".py") else None
            continue
        if line.startswith("@@"):
            flush()
            in_hunk = current_path is not None
            continue
        if not in_hunk:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:])
        else:
            flush()
    flush()
    return regions


def parse_added_python(source: str) -> ast.AST | None:
    candidates = (source, textwrap.dedent(source), "def _openswe_added_code():\n" + textwrap.indent(source, "    "))
    for candidate in candidates:
        try:
            return ast.parse(candidate)
        except (IndentationError, SyntaxError):
            continue
    return None


def dotted_name(node: ast.AST | None) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def runtime_assertion_kind(node: ast.AST) -> str | None:
    if isinstance(node, ast.Assert):
        return "assert_statement"
    if isinstance(node, ast.Raise) and dotted_name(node.exc.func if isinstance(node.exc, ast.Call) else node.exc).endswith(
        "AssertionError"
    ):
        return "raise_assertion_error"
    if not isinstance(node, ast.Call):
        return None
    name = dotted_name(node.func)
    leaf = name.rsplit(".", 1)[-1]
    if leaf.lower().startswith("assert"):
        return "assertion_call"
    if name in {"pytest.raises", "pytest.warns", "pytest.fail"}:
        return "pytest_runtime_assertion"
    if name == "sys.exit" and node.args:
        value = node.args[0]
        if isinstance(value, ast.Constant) and isinstance(value.value, int) and value.value != 0:
            return "nonzero_sys_exit"
    return None


def is_static_oracle_assertion(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and STATIC_ASSERTION_TERM_RE.search(child.id):
            return True
        if isinstance(child, ast.Attribute) and STATIC_ASSERTION_TERM_RE.search(child.attr):
            return True
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if STATIC_ORACLE_RE.search(child.value):
                return True
            if SOURCE_FILE_RE.search(child.value) and any(
                isinstance(call, ast.Call)
                and dotted_name(call.func).rsplit(".", 1)[-1] in {"open", "read_text", "read_bytes"}
                for call in ast.walk(node)
            ):
                return True
    return False


def dynamic_assertion_evidence(patch_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dynamic: list[dict[str, Any]] = []
    static: list[dict[str, Any]] = []
    for region in added_python_regions(patch_text):
        tree = parse_added_python(region["source"])
        if tree is None:
            continue
        for node in ast.walk(tree):
            kind = runtime_assertion_kind(node)
            if kind is None:
                continue
            evidence = {"path": region["path"], "kind": kind, "line": getattr(node, "lineno", None)}
            if is_static_oracle_assertion(node):
                static.append(evidence)
            else:
                dynamic.append(evidence)
    return dynamic, static


def git_read(repo: Path, *arguments: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def normalize_repository_slug(repository: str) -> str | None:
    cleaned = repository.strip().rstrip("/")
    cleaned = re.sub(r"\.git$", "", cleaned)
    cleaned = re.sub(r"^(?:https?://|ssh://git@|git@)github\.com[:/]", "", cleaned)
    cleaned = cleaned.strip("/")
    parts = [part for part in cleaned.split("/") if part]
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    if "__" in cleaned:
        owner, name = cleaned.split("__", 1)
        return f"{owner}/{name}" if owner and name else None
    return None


def locate_seed_repo(seed_repo_root: Path, repository: str) -> tuple[Path | None, str | None]:
    slug = normalize_repository_slug(repository)
    if not slug:
        return None, None
    normalized = slug.replace("/", "__")
    for candidate in (
        seed_repo_root / normalized,
        seed_repo_root / f"{normalized}.git",
        seed_repo_root / slug,
        seed_repo_root / f"{slug}.git",
    ):
        if candidate.is_dir():
            return candidate, slug
    return None, slug


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def provenance_materialization(bundle_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = bundle_dir / "repair_provenance.json"
    if not path.is_file():
        return None, "missing repair_provenance.json"
    try:
        provenance = read_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return None, f"invalid repair_provenance.json: {exc}"
    materialization = provenance.get("materialization")
    if isinstance(materialization, dict):
        return materialization, None
    if isinstance(materialization, str):
        return provenance, None
    return None, "repair_provenance lacks materialization evidence"


def parse_seed_tree(seed_repo: Path, commit: str) -> tuple[dict[str, dict[str, str]] | None, str | None]:
    result = git_read(seed_repo, "ls-tree", "-r", "-z", "--full-tree", commit)
    if result.returncode != 0:
        return None, result.stderr.strip() or "git ls-tree failed"
    entries: dict[str, dict[str, str]] = {}
    for record in result.stdout.split("\0"):
        if not record:
            continue
        metadata, separator, path = record.partition("\t")
        fields = metadata.split()
        if not separator or len(fields) != 3 or not path:
            return None, "malformed git ls-tree output"
        mode, object_type, object_oid = fields
        if object_type != "blob" or mode not in {"100644", "100755", "120000"}:
            return None, f"unsupported tree entry {path}: mode={mode} type={object_type}"
        if path in entries:
            return None, f"duplicate seed tree path: {path}"
        entries[path] = {"mode": mode, "type": object_type, "oid": object_oid.lower()}
    return entries, None


def git_blob_oid(data: bytes, object_format: str) -> str:
    if object_format not in {"sha1", "sha256"}:
        raise ValueError(f"unsupported Git object format: {object_format}")
    digest = hashlib.new(object_format)
    digest.update(f"blob {len(data)}\0".encode("ascii"))
    digest.update(data)
    return digest.hexdigest()


def materialized_paths(repo_dir: Path) -> set[str]:
    sidecars = {
        ".swe_base_commit",
        ".swe_base_tree",
        ".swe_content_manifest.json",
        ".swe_content_manifest.sha256",
        ".swe_materialization.json",
    }
    paths: set[str] = set()
    for root, directories, files in os.walk(repo_dir, topdown=True, followlinks=False):
        root_path = Path(root)
        for directory in list(directories):
            path = root_path / directory
            if path.is_symlink():
                paths.add(path.relative_to(repo_dir).as_posix())
                directories.remove(directory)
        for name in files:
            path = root_path / name
            relative = path.relative_to(repo_dir).as_posix()
            if relative not in sidecars:
                paths.add(relative)
    return paths


def compare_archive_to_seed_tree(
    repo_dir: Path,
    seed_entries: dict[str, dict[str, str]],
    object_format: str,
) -> dict[str, Any]:
    expected_paths = set(seed_entries)
    actual_paths = materialized_paths(repo_dir)
    missing = sorted(expected_paths - actual_paths)
    extra = sorted(actual_paths - expected_paths)
    mismatches: list[dict[str, str]] = []
    for relative in sorted(expected_paths & actual_paths):
        expected = seed_entries[relative]
        path = repo_dir / relative
        if expected["mode"] == "120000":
            if not path.is_symlink():
                mismatches.append({"path": relative, "reason": "expected_symlink"})
                continue
            data = os.fsencode(os.readlink(path))
            observed_mode = "120000"
        else:
            if path.is_symlink() or not path.is_file():
                mismatches.append({"path": relative, "reason": "expected_regular_file"})
                continue
            data = path.read_bytes()
            observed_mode = "100755" if path.stat().st_mode & 0o111 else "100644"
        observed_oid = git_blob_oid(data, object_format)
        if observed_mode != expected["mode"] or observed_oid != expected["oid"]:
            mismatches.append(
                {
                    "path": relative,
                    "reason": "mode_or_blob_mismatch",
                    "expected_mode": expected["mode"],
                    "observed_mode": observed_mode,
                    "expected_oid": expected["oid"],
                    "observed_oid": observed_oid,
                }
            )
    return {
        "ok": not missing and not extra and not mismatches,
        "expected_path_count": len(expected_paths),
        "observed_path_count": len(actual_paths),
        "missing_paths": missing[:100],
        "extra_paths": extra[:100],
        "mismatches": mismatches[:100],
        "evidence_truncated": len(missing) > 100 or len(extra) > 100 or len(mismatches) > 100,
    }


def embedded_repo_contract_declared(bundle_dir: Path) -> bool:
    required = {"repo/base.git.bundle", "repo/identity.json"}
    if any((bundle_dir / relative).exists() or (bundle_dir / relative).is_symlink() for relative in required):
        return True
    runtime_path = bundle_dir / "runtime_manifest.json"
    if runtime_path.exists() or runtime_path.is_symlink():
        try:
            runtime = read_json(runtime_path)
        except (OSError, ValueError, json.JSONDecodeError):
            return True
        if runtime.get("repo_identity_file") or runtime.get("repo_git_bundle_sha256"):
            return True
        identity = runtime.get("repo_identity")
        if isinstance(identity, dict) and identity.get("git_bundle"):
            return True
    manifest_path = bundle_dir / "bundle_manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = read_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return True
    files = manifest.get("files")
    return isinstance(files, list) and any(
        isinstance(entry, dict) and entry.get("path") in required for entry in files
    )


def detached_bundle_seal_evidence(
    bundle_dir: Path,
    instance_id: str,
    required_paths: tuple[str, ...],
) -> dict[str, Any]:
    manifest_path = bundle_dir / "bundle_manifest.json"
    seal_path = bundle_dir / "bundle_manifest.sha256"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("embedded repository lacks regular bundle_manifest.json")
    if not seal_path.is_file() or seal_path.is_symlink():
        raise ValueError("embedded repository lacks detached bundle_manifest.sha256")
    try:
        seal_text = seal_path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"detached bundle seal is unreadable: {exc}") from exc
    match = re.fullmatch(r"([0-9a-f]{64})  bundle_manifest\.json\n?", seal_text)
    if match is None:
        raise ValueError("detached bundle seal has an invalid format")
    observed_manifest_sha256 = sha256_file(manifest_path)
    if match.group(1) != observed_manifest_sha256:
        raise ValueError("detached bundle seal does not match bundle_manifest.json")

    manifest = read_json(manifest_path)
    if str(manifest.get("instance_id") or "") != instance_id:
        raise ValueError("detached bundle manifest instance identity mismatch")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("detached bundle manifest lacks a files array")
    indexed: dict[str, dict[str, Any]] = {}
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("detached bundle manifest contains an invalid file entry")
        relative = entry["path"]
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or path.as_posix() != relative:
            raise ValueError("detached bundle manifest contains an unsafe path")
        if relative in indexed:
            raise ValueError(f"detached bundle manifest contains duplicate path: {relative}")
        indexed[relative] = entry

    sealed_files: dict[str, str] = {}
    for relative in required_paths:
        entry = indexed.get(relative)
        path = bundle_dir / relative
        if entry is None:
            raise ValueError(f"detached bundle manifest does not cover {relative}")
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"sealed embedded repository file is missing or not regular: {relative}")
        expected_sha256 = str(entry.get("sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise ValueError(f"detached bundle manifest has invalid SHA256 for {relative}")
        observed_sha256 = sha256_file(path)
        if observed_sha256 != expected_sha256:
            raise ValueError(f"detached bundle manifest SHA256 mismatch for {relative}")
        sealed_files[relative] = observed_sha256
    if manifest.get("schema") != "openswe-bundle-manifest-v2":
        raise ValueError("unsupported embedded bundle manifest schema")
    scope = manifest.get("scope")
    if not isinstance(scope, dict) or scope.get("recursive") is not True:
        raise ValueError("embedded bundle manifest is not recursive")
    actual_entries = embedded_delivery_entries(bundle_dir)
    if files != actual_entries:
        raise ValueError("recursive bundle payload seal mismatch")
    payload_sha256 = hashlib.sha256(
        json.dumps(actual_entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if manifest.get("candidate_payload_sha256") != payload_sha256:
        raise ValueError("candidate payload digest mismatch")
    return {
        "detached_seal_path": "bundle_manifest.sha256",
        "bundle_manifest_sha256": observed_manifest_sha256,
        "sealed_files": sealed_files,
        "recursive_payload_verified": True,
        "candidate_payload_sha256": payload_sha256,
    }


def recursive_worktree_snapshot(
    root: Path,
    excluded_relative_paths: set[str],
) -> dict[str, dict[str, str]]:
    snapshot: dict[str, dict[str, str]] = {}
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for directory in list(directories):
            path = current_path / directory
            relative = path.relative_to(root).as_posix()
            if relative == ".git" or relative.startswith(".git/") or relative in excluded_relative_paths:
                directories.remove(directory)
                continue
            if path.is_symlink():
                target = os.fsencode(os.readlink(path))
                snapshot[relative] = {
                    "mode": "120000",
                    "sha256": hashlib.sha256(target).hexdigest(),
                }
                directories.remove(directory)
        for name in files:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if relative == ".git" or relative.startswith(".git/") or relative in excluded_relative_paths:
                continue
            if path.is_symlink():
                target = os.fsencode(os.readlink(path))
                snapshot[relative] = {
                    "mode": "120000",
                    "sha256": hashlib.sha256(target).hexdigest(),
                }
            elif path.is_file():
                snapshot[relative] = {
                    "mode": "100755" if path.stat().st_mode & 0o111 else "100644",
                    "sha256": sha256_file(path),
                }
            else:
                raise ValueError(f"unsupported repository entry: {relative}")
    return snapshot


def compare_embedded_delivery_tree(checkout_dir: Path, delivery_repo_dir: Path) -> dict[str, Any]:
    expected = recursive_worktree_snapshot(checkout_dir, set())
    excluded = {"base.git.bundle", "identity.json"}
    if ".swe_base_commit" not in expected:
        excluded.add(".swe_base_commit")
    observed = recursive_worktree_snapshot(delivery_repo_dir, excluded)
    expected_paths = set(expected)
    observed_paths = set(observed)
    missing = sorted(expected_paths - observed_paths)
    extra = sorted(observed_paths - expected_paths)
    mismatches = [
        {
            "path": relative,
            "expected": expected[relative],
            "observed": observed[relative],
        }
        for relative in sorted(expected_paths & observed_paths)
        if expected[relative] != observed[relative]
    ]
    return {
        "ok": not missing and not extra and not mismatches,
        "expected_path_count": len(expected_paths),
        "observed_path_count": len(observed_paths),
        "missing_paths": missing[:100],
        "extra_paths": extra[:100],
        "mismatches": mismatches[:100],
        "evidence_truncated": len(missing) > 100 or len(extra) > 100 or len(mismatches) > 100,
    }


def embedded_delivery_entries(bundle_dir: Path) -> list[dict[str, Any]]:
    excluded_roots = {".git", "validation"}
    excluded_files = {"bundle_manifest.json", "bundle_manifest.sha256"}
    entries: list[dict[str, Any]] = []
    for root, directory_names, file_names in os.walk(bundle_dir, topdown=True, followlinks=False):
        root_path = Path(root)
        relative_root = root_path.relative_to(bundle_dir)
        symlink_directories = [name for name in directory_names if (root_path / name).is_symlink()]
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in symlink_directories
            and not (relative_root == Path(".") and name in excluded_roots)
            and not (relative_root == Path("repo") and name == ".git")
        )
        for name in sorted(symlink_directories):
            path = root_path / name
            relative = path.relative_to(bundle_dir).as_posix()
            target = os.readlink(path)
            target_bytes = os.fsencode(target)
            entries.append(
                {
                    "path": relative,
                    "type": "symlink",
                    "mode": f"{path.lstat().st_mode & 0o7777:04o}",
                    "bytes": len(target_bytes),
                    "sha256": hashlib.sha256(target_bytes).hexdigest(),
                }
            )
        for name in sorted(file_names):
            path = root_path / name
            relative = path.relative_to(bundle_dir).as_posix()
            if relative in excluded_files or relative.split("/", 1)[0] in excluded_roots or relative == "repo/.git":
                continue
            mode = path.lstat().st_mode & 0o7777
            if path.is_symlink():
                target_bytes = os.fsencode(os.readlink(path))
                entries.append(
                    {
                        "path": relative,
                        "type": "symlink",
                        "mode": f"{mode:04o}",
                        "bytes": len(target_bytes),
                        "sha256": hashlib.sha256(target_bytes).hexdigest(),
                    }
                )
            elif path.is_file():
                entries.append(
                    {
                        "path": relative,
                        "type": "file",
                        "mode": f"{mode:04o}",
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
            else:
                raise ValueError(f"unsupported delivery entry: {relative}")
    entries.sort(key=lambda entry: str(entry["path"]))
    return entries


def embedded_git_tree_oid(repo_dir: Path) -> str:
    sidecars = {
        ".swe_base_commit",
        ".swe_base_tree",
        ".swe_content_manifest.json",
        ".swe_content_manifest.sha256",
        ".swe_materialization.json",
    }

    def object_oid(kind: str, data: bytes) -> str:
        digest = hashlib.sha1()
        digest.update(f"{kind} {len(data)}\0".encode("ascii"))
        digest.update(data)
        return digest.hexdigest()

    def tree_oid(directory: Path, root: bool = False) -> str | None:
        records: list[tuple[bytes, bytes]] = []
        for path in directory.iterdir():
            name = path.name
            if name == ".git" or (root and name in sidecars):
                continue
            name_bytes = os.fsencode(name)
            if path.is_symlink():
                mode = "120000"
                oid = object_oid("blob", os.fsencode(os.readlink(path)))
                sort_key = name_bytes + b"\0"
            elif path.is_dir():
                oid = tree_oid(path)
                if oid is None:
                    continue
                mode = "40000"
                sort_key = name_bytes + b"/"
            elif path.is_file():
                mode = "100755" if path.stat().st_mode & 0o111 else "100644"
                oid = object_oid("blob", path.read_bytes())
                sort_key = name_bytes + b"\0"
            else:
                raise ValueError(f"unsupported repository entry: {path.relative_to(repo_dir).as_posix()}")
            record = mode.encode("ascii") + b" " + name_bytes + b"\0" + bytes.fromhex(oid)
            records.append((sort_key, record))
        if not records:
            return None
        body = b"".join(record for _, record in sorted(records, key=lambda item: item[0]))
        return object_oid("tree", body)

    observed = tree_oid(repo_dir, root=True)
    if observed is None:
        raise ValueError("embedded repository tree is empty")
    return observed


def verify_embedded_archive_attestation(
    bundle_dir: Path,
    task: dict[str, Any],
    materialization: dict[str, Any],
) -> dict[str, Any]:
    manifest_path = bundle_dir / "bundle_manifest.json"
    checksum_path = bundle_dir / "bundle_manifest.sha256"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return {"ok": False, "reason": "missing detached bundle manifest"}
    if not checksum_path.is_file() or checksum_path.is_symlink():
        return {"ok": False, "reason": "missing detached bundle manifest checksum"}
    try:
        checksum_text = checksum_path.read_text(encoding="ascii")
        checksum_match = re.fullmatch(r"([0-9a-f]{64})  bundle_manifest\.json\n?", checksum_text)
        if checksum_match is None or checksum_match.group(1) != sha256_file(manifest_path):
            return {"ok": False, "reason": "detached bundle manifest checksum mismatch"}
        manifest = read_json(manifest_path)
        if manifest.get("schema") != "openswe-bundle-manifest-v2":
            return {"ok": False, "reason": "unsupported embedded bundle manifest schema"}
        if manifest.get("instance_id") != bundle_dir.name:
            return {"ok": False, "reason": "bundle manifest instance identity mismatch"}
        scope = manifest.get("scope")
        if not isinstance(scope, dict) or scope.get("recursive") is not True:
            return {"ok": False, "reason": "bundle manifest is not recursive"}
        exclusions = scope.get("excluded")
        required_exclusions = {".git/", "validation/", "bundle_manifest.json", "bundle_manifest.sha256"}
        if not isinstance(exclusions, list) or not required_exclusions.issubset(set(exclusions)):
            return {"ok": False, "reason": "bundle manifest scope exclusions are incomplete"}
        actual_entries = embedded_delivery_entries(bundle_dir)
        if manifest.get("files") != actual_entries:
            return {"ok": False, "reason": "recursive bundle payload seal mismatch"}
        payload_sha256 = hashlib.sha256(
            json.dumps(actual_entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if manifest.get("candidate_payload_sha256") != payload_sha256:
            return {"ok": False, "reason": "candidate payload digest mismatch"}
        if not any(str(entry.get("path") or "").startswith("repo/") for entry in actual_entries):
            return {"ok": False, "reason": "recursive seal contains no embedded repository"}

        repository = str(task.get("repo") or task.get("repository") or "").strip()
        base_commit = str(task.get("base_commit") or "").strip().lower()
        if not repository or re.fullmatch(r"[0-9a-f]{40}", base_commit) is None:
            return {"ok": False, "reason": "embedded attestation requires a declared 40-character base commit"}
        runtime = read_json(bundle_dir / "runtime_manifest.json")
        runtime_materialization = runtime.get("repository_materialization")
        if not isinstance(runtime_materialization, dict):
            return {"ok": False, "reason": "runtime manifest lacks repository materialization attestation"}
        if runtime.get("base_commit") != base_commit or runtime.get("repository") != repository:
            return {"ok": False, "reason": "runtime and task repository identities differ"}

        method = str(materialization.get("materialization") or materialization.get("materialization_method") or "")
        commit = str(materialization.get("resolved_base_commit") or "").lower()
        tree = str(materialization.get("tree_oid") or "").lower()
        archive = str(materialization.get("archive_sha256") or "").lower()
        runtime_method = str(
            runtime_materialization.get("materialization")
            or runtime_materialization.get("materialization_method")
            or ""
        )
        runtime_commit = str(runtime_materialization.get("resolved_base_commit") or "").lower()
        runtime_tree = str(runtime_materialization.get("tree_oid") or "").lower()
        runtime_archive = str(runtime_materialization.get("archive_sha256") or "").lower()
        if method != "git_archive_exact_seed_commit" or runtime_method != method:
            return {"ok": False, "reason": "embedded archive materialization method mismatch"}
        if commit != base_commit or runtime_commit != base_commit:
            return {"ok": False, "reason": "embedded archive commit attestation mismatch"}
        if re.fullmatch(r"[0-9a-f]{40}", tree) is None or runtime_tree != tree:
            return {"ok": False, "reason": "embedded archive tree attestation mismatch"}
        if re.fullmatch(r"[0-9a-f]{64}", archive) is None or runtime_archive != archive:
            return {"ok": False, "reason": "embedded archive digest attestation mismatch"}
        tree_hash = materialization.get("tree_oid_sha256")
        if not isinstance(tree_hash, str) or tree_hash.lower() != hashlib.sha256(tree.encode("utf-8")).hexdigest():
            return {"ok": False, "reason": "embedded tree attestation hash mismatch"}
        observed_tree = embedded_git_tree_oid(bundle_dir / "repo")
        if observed_tree != tree:
            return {"ok": False, "reason": "embedded repository content does not match attested tree OID"}
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "reason": f"embedded archive attestation is unreadable: {exc}"}
    return {
        "ok": True,
        "bundle_manifest_sha256": checksum_match.group(1),
        "candidate_payload_sha256": payload_sha256,
        "observed_tree_oid": observed_tree,
        "archive_sha256": archive,
    }


def repo_identity_failure(
    status: str,
    failure_class: str,
    reason: str,
    **evidence: Any,
) -> dict[str, Any]:
    return {
        "status": status,
        "failure_class": failure_class,
        "reason": reason,
        "counts_as_swe_attempt": False,
        "counts_as_behavior_failure": False,
        "test_execution_allowed": False,
        **evidence,
    }


def verify_embedded_repo_identity(
    bundle_dir: Path,
    task: dict[str, Any],
    repository: str,
    base_commit: str,
) -> dict[str, Any]:
    instance_id = str(task.get("instance_id") or task.get("id") or bundle_dir.name).strip()
    repo_dir = bundle_dir / "repo"
    git_bundle_path = repo_dir / "base.git.bundle"
    identity_path = repo_dir / "identity.json"
    try:
        seal = detached_bundle_seal_evidence(
            bundle_dir,
            instance_id,
            ("repo/base.git.bundle", "repo/identity.json", "repo/.swe_base_commit"),
        )
        identity = read_json(identity_path)
        if (repo_dir / ".swe_base_commit").read_text(encoding="ascii").strip() != base_commit:
            raise ValueError("embedded repository commit sentinel differs from task base commit")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            str(exc),
            materialization_mode="embedded_archive_attested",
        )

    identity_repository = str(identity.get("repository_slug") or "").strip()
    identity_commit = str(identity.get("base_commit") or "").strip()
    identity_tree = str(identity.get("base_tree") or "").strip()
    identity_bundle_sha256 = str(identity.get("git_bundle_sha256") or "").strip()
    object_format = str(identity.get("object_format") or "").strip()
    normalized_task_repository = normalize_repository_slug(repository)
    normalized_identity_repository = normalize_repository_slug(identity_repository)
    if (
        not normalized_task_repository
        or identity_repository != normalized_identity_repository
        or normalized_identity_repository != normalized_task_repository
    ):
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            "embedded repository slug does not exactly match task repository",
            materialization_mode="embedded_archive_attested",
            expected_repository=normalized_task_repository,
            observed_repository=identity_repository,
        )
    if not re.fullmatch(r"[0-9a-f]{40}", identity_commit) or identity_commit != base_commit:
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            "embedded repository identity requires the exact 40-hex task base commit",
            materialization_mode="embedded_archive_attested",
            expected_base_commit=base_commit,
            observed_base_commit=identity_commit,
        )
    if object_format not in {"sha1", "sha256"}:
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            "embedded repository object format is missing or unsupported",
            materialization_mode="embedded_archive_attested",
            object_format=object_format,
        )
    oid_width = 40 if object_format == "sha1" else 64
    if not re.fullmatch(rf"[0-9a-f]{{{oid_width}}}", identity_tree):
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            "embedded repository tree OID does not match its object format",
            materialization_mode="embedded_archive_attested",
            object_format=object_format,
            observed_tree_oid=identity_tree,
        )
    if not re.fullmatch(r"[0-9a-f]{64}", identity_bundle_sha256):
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            "embedded Git bundle identity lacks a valid SHA256",
            materialization_mode="embedded_archive_attested",
        )
    observed_bundle_sha256 = sha256_file(git_bundle_path)
    if (
        observed_bundle_sha256 != identity_bundle_sha256
        or seal["sealed_files"]["repo/base.git.bundle"] != identity_bundle_sha256
    ):
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            "embedded Git bundle SHA256 differs from sealed repository identity",
            materialization_mode="embedded_archive_attested",
            expected_git_bundle_sha256=identity_bundle_sha256,
            observed_git_bundle_sha256=observed_bundle_sha256,
        )

    validation_root = bundle_dir / "validation"
    try:
        validation_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".embedded-repo-", dir=str(validation_root)) as temporary:
            temporary_root = Path(temporary)
            verification_repo = temporary_root / "verify.git"
            checkout_dir = temporary_root / "checkout"
            init_result = subprocess.run(
                ["git", "init", "--quiet", "--bare", str(verification_repo)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
                check=False,
            )
            if init_result.returncode != 0:
                return repo_identity_failure(
                    "infra_requeue",
                    "infrastructure",
                    "unable to initialize temporary repository for Git bundle verification",
                    materialization_mode="embedded_archive_attested",
                )
            bundle_verify = git_read(verification_repo, "bundle", "verify", str(git_bundle_path))
            if bundle_verify.returncode != 0:
                return repo_identity_failure(
                    "repo_identity_rejected",
                    "repo_identity",
                    "offline git bundle verify failed or bundle has unavailable prerequisites",
                    materialization_mode="embedded_archive_attested",
                    git_bundle_verify_stderr=bundle_verify.stderr[-2000:],
                )
            clone_result = subprocess.run(
                ["git", "clone", "--quiet", "--no-checkout", str(git_bundle_path), str(checkout_dir)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
                check=False,
            )
            if clone_result.returncode != 0:
                return repo_identity_failure(
                    "repo_identity_rejected",
                    "repo_identity",
                    "offline clone from embedded Git bundle failed",
                    materialization_mode="embedded_archive_attested",
                    git_clone_stderr=clone_result.stderr[-2000:],
                )
            resolved_commit = git_read(checkout_dir, "rev-parse", "--verify", f"{base_commit}^{{commit}}")
            checkout_result = git_read(checkout_dir, "checkout", "--quiet", "--detach", base_commit)
            observed_head_result = git_read(checkout_dir, "rev-parse", "--verify", "HEAD")
            observed_tree_result = git_read(checkout_dir, "rev-parse", "--verify", "HEAD^{tree}")
            object_format_result = git_read(checkout_dir, "rev-parse", "--show-object-format")
            observed_object_format = object_format_result.stdout.strip()
            if object_format_result.returncode == 0 and observed_object_format == "--show-object-format":
                # Older Git echoes unknown rev-parse flags. Repositories without
                # an objectFormat extension use SHA-1; do not accept arbitrary output.
                format_config = git_read(checkout_dir, "config", "--get", "extensions.objectFormat")
                if format_config.returncode == 1 and not format_config.stdout.strip():
                    observed_object_format = "sha1"
            if (
                resolved_commit.returncode != 0
                or resolved_commit.stdout.strip() != base_commit
                or checkout_result.returncode != 0
                or observed_head_result.returncode != 0
                or observed_head_result.stdout.strip() != base_commit
                or observed_tree_result.returncode != 0
                or observed_tree_result.stdout.strip() != identity_tree
                or object_format_result.returncode != 0
                or observed_object_format != object_format
            ):
                return repo_identity_failure(
                    "repo_identity_rejected",
                    "repo_identity",
                    "embedded Git bundle checkout identity does not match commit, tree, or object format",
                    materialization_mode="embedded_archive_attested",
                    expected_base_commit=base_commit,
                    observed_head=observed_head_result.stdout.strip(),
                    expected_tree_oid=identity_tree,
                    observed_tree_oid=observed_tree_result.stdout.strip(),
                    expected_object_format=object_format,
                    observed_object_format=observed_object_format,
                )
            unstaged = git_read(checkout_dir, "diff", "--quiet")
            staged = git_read(checkout_dir, "diff", "--cached", "--quiet")
            untracked = git_read(checkout_dir, "ls-files", "--others", "--exclude-standard")
            if (
                unstaged.returncode != 0
                or staged.returncode != 0
                or untracked.returncode != 0
                or bool(untracked.stdout.strip())
            ):
                return repo_identity_failure(
                    "repo_identity_rejected",
                    "repo_identity",
                    "fresh embedded Git bundle checkout is not clean",
                    materialization_mode="embedded_archive_attested",
                )
            content_proof = compare_embedded_delivery_tree(checkout_dir, repo_dir)
            if not content_proof["ok"]:
                return repo_identity_failure(
                    "repo_identity_rejected",
                    "repo_identity",
                    "delivered repository worktree differs from fresh embedded bundle checkout",
                    materialization_mode="embedded_archive_attested",
                    content_proof=content_proof,
                )
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return repo_identity_failure(
            "infra_requeue",
            "infrastructure",
            f"embedded repository verification could not complete: {exc}",
            materialization_mode="embedded_archive_attested",
        )

    return {
        "status": "passed",
        "failure_class": "none",
        "materialization_mode": "embedded_archive_attested",
        "expected_base_commit": base_commit,
        "observed_head": base_commit,
        "head_check_applicable": True,
        "expected_tree_oid": identity_tree,
        "observed_tree_oid": identity_tree,
        "object_format": object_format,
        "repository_slug": identity_repository,
        "git_bundle_sha256": observed_bundle_sha256,
        "detached_bundle_seal": seal,
        "content_verified": True,
        "content_proof": content_proof,
        "clean_baseline": True,
        "external_seed_used": False,
        "counts_as_swe_attempt": False,
        "test_execution_allowed": True,
    }


def verify_repo_identity(bundle_dir: Path, task: dict[str, Any], seed_repo_root: Path | None) -> dict[str, Any]:
    repo_dir = bundle_dir / "repo"
    repository = str(task.get("repo") or task.get("repository") or "").strip()
    base_commit = str(task.get("base_commit") or "").strip().lower()
    if not repository or not re.fullmatch(r"[0-9a-f]{40}", base_commit):
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            "task repository or full base_commit identity is missing",
            materialization_mode="unknown",
        )
    if not repo_dir.is_dir():
        return repo_identity_failure(
            "repo_identity_rejected", "repo_identity", "bundle repo directory is missing", materialization_mode="unknown"
        )

    # A declared embedded contract always wins, even when .git is present.
    # Invalid embedded payloads must not fall back to a legacy checkout.
    if embedded_repo_contract_declared(bundle_dir):
        return verify_embedded_repo_identity(bundle_dir, task, repository, base_commit)

    head = git_read(repo_dir, "rev-parse", "--verify", "HEAD")
    if head.returncode == 0:
        resolved = git_read(repo_dir, "rev-parse", "--verify", f"{base_commit}^{{commit}}")
        if resolved.returncode != 0 or resolved.stdout.strip().lower() != base_commit:
            return repo_identity_failure(
                "repo_identity_rejected",
                "repo_identity",
                "declared base_commit is not the exact commit in bundle repo",
                materialization_mode="git_checkout",
                observed_head=head.stdout.strip(),
            )
        observed_head = head.stdout.strip().lower()
        if observed_head != base_commit:
            return repo_identity_failure(
                "repo_identity_rejected",
                "repo_identity",
                "bundle HEAD does not equal task base_commit",
                materialization_mode="git_checkout",
                observed_head=observed_head,
                expected_base_commit=base_commit,
            )
        head_tree = git_read(repo_dir, "rev-parse", "--verify", "HEAD^{tree}")
        base_tree = git_read(repo_dir, "rev-parse", "--verify", f"{base_commit}^{{tree}}")
        if head_tree.returncode != 0 or base_tree.returncode != 0 or head_tree.stdout.strip() != base_tree.stdout.strip():
            return repo_identity_failure(
                "repo_identity_rejected",
                "repo_identity",
                "bundle HEAD tree does not match base_commit tree",
                materialization_mode="git_checkout",
            )
        unstaged = git_read(repo_dir, "diff", "--quiet")
        staged = git_read(repo_dir, "diff", "--cached", "--quiet")
        untracked = git_read(repo_dir, "ls-files", "--others", "--exclude-standard")
        allowed_sidecars = {".swe_base_commit", ".swe_base_tree", ".swe_materialization.json"}
        unexpected_untracked = sorted(
            path for path in untracked.stdout.splitlines() if path.strip() and path.strip() not in allowed_sidecars
        )
        if unstaged.returncode != 0 or staged.returncode != 0 or untracked.returncode != 0 or unexpected_untracked:
            return repo_identity_failure(
                "repo_identity_rejected",
                "repo_identity",
                "bundle Git checkout is not a clean baseline",
                materialization_mode="git_checkout",
                unexpected_untracked=unexpected_untracked[:100],
            )
        return {
            "status": "passed",
            "failure_class": "none",
            "materialization_mode": "git_checkout",
            "expected_base_commit": base_commit,
            "observed_head": observed_head,
            "head_check_applicable": True,
            "expected_tree_oid": base_tree.stdout.strip(),
            "observed_tree_oid": head_tree.stdout.strip(),
            "content_verified": True,
            "clean_baseline": True,
            "counts_as_swe_attempt": False,
            "test_execution_allowed": True,
        }

    sentinel = repo_dir / ".swe_base_commit"
    if not sentinel.is_file():
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            "archive bundle lacks .swe_base_commit",
            materialization_mode="archive_attested",
        )
    observed_commit = sentinel.read_text(encoding="utf-8").strip().lower()
    if observed_commit != base_commit:
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            "archive base commit marker does not equal task base_commit",
            materialization_mode="archive_attested",
            observed_commit=observed_commit,
            expected_base_commit=base_commit,
        )
    materialization, provenance_error = provenance_materialization(bundle_dir)
    if materialization is None:
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            provenance_error or "missing archive materialization evidence",
            materialization_mode="archive_attested",
        )
    method = str(materialization.get("materialization") or materialization.get("materialization_method") or "")
    provenance_commit = str(materialization.get("resolved_base_commit") or "").lower()
    provenance_tree = str(materialization.get("tree_oid") or "").lower()
    provenance_archive = str(materialization.get("archive_sha256") or "").lower()
    if method != "git_archive_exact_seed_commit" or not provenance_tree or not provenance_archive or provenance_commit != base_commit:
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            "repair provenance lacks exact archive method, commit, tree OID, or archive digest",
            materialization_mode="archive_attested",
            provenance_method=method,
        )
    embedded_attestation = verify_embedded_archive_attestation(bundle_dir, task, materialization)
    if not embedded_attestation["ok"]:
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            str(embedded_attestation["reason"]),
            materialization_mode="archive_attested",
            embedded_attestation_status="rejected",
        )
    return {
        "status": "passed",
        "failure_class": "none",
        "materialization_mode": "archive_attested",
        "attestation_source": "embedded_recursive_bundle_seal",
        "provenance_materialization": method,
        "expected_base_commit": base_commit,
        "observed_head": None,
        "head_check_applicable": False,
        "expected_tree_oid": provenance_tree,
        "observed_tree_oid": embedded_attestation["observed_tree_oid"],
        "archive_sha256": embedded_attestation["archive_sha256"],
        "bundle_manifest_sha256": embedded_attestation["bundle_manifest_sha256"],
        "candidate_payload_sha256": embedded_attestation["candidate_payload_sha256"],
        "content_verified": True,
        "content_proof": {"recursive_bundle_seal": True, "git_tree_oid_reconstructed": True},
        "clean_baseline": True,
        "counts_as_swe_attempt": False,
        "test_execution_allowed": True,
    }
    if seed_repo_root is None:
        return repo_identity_failure(
            "infra_requeue",
            "infrastructure",
            "archive identity requires --seed-repo-root",
            materialization_mode="archive_attested",
        )
    seed_repo, normalized_repository = locate_seed_repo(seed_repo_root, repository)
    if seed_repo is None:
        return repo_identity_failure(
            "infra_requeue",
            "infrastructure",
            "matching seed repository is missing",
            materialization_mode="archive_attested",
            normalized_repository=normalized_repository,
        )
    seed_commit = git_read(seed_repo, "rev-parse", "--verify", f"{base_commit}^{{commit}}")
    if seed_commit.returncode != 0 or seed_commit.stdout.strip().lower() != base_commit:
        return repo_identity_failure(
            "infra_requeue",
            "infrastructure",
            "exact base commit is missing from seed repository",
            materialization_mode="archive_attested",
            normalized_repository=normalized_repository,
        )
    seed_tree = git_read(seed_repo, "rev-parse", "--verify", f"{base_commit}^{{tree}}")
    if seed_tree.returncode != 0:
        return repo_identity_failure(
            "infra_requeue", "infrastructure", "seed commit tree is unreadable", materialization_mode="archive_attested"
        )
    observed_tree = seed_tree.stdout.strip().lower()
    if observed_tree != provenance_tree:
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            "repair provenance tree OID differs from exact seed commit tree",
            materialization_mode="archive_attested",
            expected_tree_oid=provenance_tree,
            observed_tree_oid=observed_tree,
        )
    object_format_result = git_read(seed_repo, "rev-parse", "--show-object-format")
    reported_object_format = object_format_result.stdout.strip()
    object_format_source = "git_rev_parse"
    if object_format_result.returncode == 0 and reported_object_format in {"sha1", "sha256"}:
        object_format = reported_object_format
    else:
        object_format_error = "\n".join(
            value for value in (object_format_result.stdout, object_format_result.stderr) if value
        ).lower()
        literal_unparsed_option = (
            object_format_result.returncode == 0
            and reported_object_format == "--show-object-format"
        )
        unsupported_option = literal_unparsed_option or (
            "--show-object-format" in object_format_error
            and any(
                signal in object_format_error
                for signal in (
                    "unknown option",
                    "unrecognized option",
                    "unknown revision or path",
                    "bad option",
                )
            )
        )
        sha1_identity = all(
            re.fullmatch(r"[0-9a-f]{40}", oid) is not None
            for oid in (base_commit, observed_tree, provenance_tree)
        )
        if not unsupported_option or not sha1_identity:
            return repo_identity_failure(
                "infra_requeue",
                "infrastructure",
                "seed Git object format is unavailable or not safely inferable",
                materialization_mode="archive_attested",
                object_format_returncode=object_format_result.returncode,
                object_format_error=object_format_error[-1000:],
            )
        object_format = "sha1"
        object_format_source = "legacy_git_40_hex_oid_fallback"
    seed_entries, tree_error = parse_seed_tree(seed_repo, base_commit)
    if seed_entries is None:
        return repo_identity_failure(
            "infra_requeue",
            "infrastructure",
            tree_error or "seed tree content is unavailable",
            materialization_mode="archive_attested",
        )
    with tempfile.TemporaryDirectory(prefix="openswe-archive-proof-") as temporary:
        archive_path = Path(temporary) / "seed.tar"
        with archive_path.open("wb") as archive_handle:
            archive_result = subprocess.run(
                ["git", "-C", str(seed_repo), "archive", "--format=tar", base_commit],
                stdout=archive_handle,
                stderr=subprocess.PIPE,
                timeout=120,
                check=False,
            )
        if archive_result.returncode != 0:
            return repo_identity_failure(
                "infra_requeue",
                "infrastructure",
                "git archive failed for exact seed commit",
                materialization_mode="archive_attested",
            )
        observed_archive = sha256_file(archive_path)
    if observed_archive != provenance_archive:
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            "repair provenance archive digest differs from exact seed archive",
            materialization_mode="archive_attested",
            expected_archive_sha256=provenance_archive,
            observed_archive_sha256=observed_archive,
        )
    content_proof = compare_archive_to_seed_tree(repo_dir, seed_entries, object_format)
    if not content_proof["ok"]:
        return repo_identity_failure(
            "repo_identity_rejected",
            "repo_identity",
            "archive repository content differs from exact seed commit tree",
            materialization_mode="archive_attested",
            content_proof=content_proof,
        )
    return {
        "status": "passed",
        "failure_class": "none",
        "materialization_mode": "archive_attested",
        "provenance_materialization": method,
        "expected_base_commit": base_commit,
        "observed_head": None,
        "head_check_applicable": False,
        "expected_tree_oid": provenance_tree,
        "observed_tree_oid": observed_tree,
        "archive_sha256": observed_archive,
        "object_format": object_format,
        "object_format_source": object_format_source,
        "content_verified": True,
        "content_proof": content_proof,
        "clean_baseline": True,
        "counts_as_swe_attempt": False,
        "test_execution_allowed": True,
    }


def quality_gate_result(bundle_dir: Path, task: dict[str, Any]) -> dict[str, Any]:
    metadata = read_json(bundle_dir / "metadata.json")
    test_patch = (bundle_dir / "test_patch.diff").read_text(encoding="utf-8")
    patch_paths = sorted(
        {
            match.group(1)
            for match in re.finditer(r"(?m)^\+\+\+ b/(.+)$", test_patch)
            if match.group(1) != "/dev/null"
        }
    )
    recorded_paths = task.get("test_patch_paths") or metadata.get("test_patch_paths") or patch_paths
    if not isinstance(recorded_paths, list):
        recorded_paths = []
    quality_values = [
        str(value)
        for value in (task.get("verifier_quality"), metadata.get("verifier_quality"))
        if value not in (None, "")
    ]
    status_values = [
        str(value)
        for value in (task.get("verifier_quality_status"), metadata.get("verifier_quality_status"))
        if value not in (None, "")
    ]
    dynamic_evidence, static_evidence = dynamic_assertion_evidence(test_patch)
    normalized_statuses = {value.strip().lower() for value in status_values}
    normalized_quality = {value.strip().lower() for value in quality_values}
    reasons: list[str] = []
    if static_evidence:
        reasons.append("static_oracle_signal")
    if not any(TEST_PATH_RE.search(str(path)) for path in recorded_paths):
        reasons.append("missing_behavior_test_path")
    if not dynamic_evidence:
        reasons.append("missing_positive_dynamic_assertion")
    if not normalized_statuses or not normalized_statuses.intersection(VALIDATION_CANDIDATE_STATUSES):
        reasons.append("quality_gate_not_validation_candidate")
    if normalized_statuses.intersection(REJECTED_QUALITY_STATUSES) or "unknown_non_static" in normalized_quality:
        reasons.append("rejected_quality_state")
    return {
        "ok": not reasons,
        "status": "validation_candidate" if not reasons else "quality_rejected",
        "reasons": sorted(set(reasons)),
        "quality_values": quality_values,
        "status_values": status_values,
        "test_patch_paths": recorded_paths,
        "has_positive_dynamic_assertion": bool(dynamic_evidence),
        "dynamic_assertion_evidence": dynamic_evidence,
        "static_assertion_evidence": static_evidence,
    }


def apply_command(cwd: Path, patch: Path, check: bool) -> dict[str, Any]:
    command = ["git", "apply", "--whitespace=nowarn"]
    if check:
        command.append("--check")
    command.append(str(patch.resolve()))
    proc = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )
    return {
        "command": command,
        "returncode": proc.returncode,
        "output_tail": "\n".join(proc.stdout.splitlines()[-80:]),
    }


def patch_sequence_preflight(
    bundle_dir: Path,
    task: dict[str, Any],
    mode: str,
    repo_identity: dict[str, Any],
) -> dict[str, Any]:
    repo_dir = bundle_dir / "repo"
    base_commit = str(task.get("base_commit") or "")
    result: dict[str, Any] = {
        "mode": mode,
        "status": "patch_apply_rejected",
        "failure_class": "patch_apply",
        "base_commit": base_commit,
        "actual_head": repo_identity.get("observed_head"),
        "base_tree_oid": repo_identity.get("observed_tree_oid"),
        "materialization_mode": repo_identity.get("materialization_mode"),
        "repo_identity_status": repo_identity.get("status"),
        "clean_worktree": repo_identity.get("clean_baseline") is True,
        "checks": [],
    }
    if repo_identity.get("status") != "passed" or repo_identity.get("test_execution_allowed") is not True:
        result["status"] = str(repo_identity.get("status") or "repo_identity_rejected")
        result["failure_class"] = str(repo_identity.get("failure_class") or "repo_identity")
        result["reason"] = str(repo_identity.get("reason") or "repository identity did not pass")
        return result

    patch_names = ["test_patch.diff"] if mode == "testonly" else ["gold_patch.diff", "test_patch.diff"]
    for patch_name in patch_names:
        patch_path = bundle_dir / patch_name
        if not patch_path.is_file() or not patch_path.read_text(encoding="utf-8").strip():
            result["reason"] = f"missing_or_empty_{patch_name}"
            return result

    with tempfile.TemporaryDirectory(prefix=f"openswe-{safe_name(bundle_dir.name)}-{mode}-") as temp:
        worktree = Path(temp) / "testbed"
        shutil.copytree(repo_dir, worktree, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        init = subprocess.run(
            ["git", "init", "-q"],
            cwd=worktree,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        if init.returncode != 0:
            result["reason"] = "temporary_git_init_failed"
            result["infra_status"] = "infra_requeue"
            result["init_output_tail"] = "\n".join(init.stdout.splitlines()[-80:])
            return result
        result["temporary_git_identity_authoritative"] = False
        result["temporary_git_purpose"] = "git_apply_only"
        for patch_name in patch_names:
            patch_path = bundle_dir / patch_name
            check_result = apply_command(worktree, patch_path, check=True)
            check_result["patch"] = patch_name
            check_result["operation"] = "check"
            result["checks"].append(check_result)
            if check_result["returncode"] != 0:
                result["reason"] = f"{patch_name}_check_failed"
                return result
            apply_result = apply_command(worktree, patch_path, check=False)
            apply_result["patch"] = patch_name
            apply_result["operation"] = "apply"
            result["checks"].append(apply_result)
            if apply_result["returncode"] != 0:
                result["reason"] = f"{patch_name}_apply_failed"
                return result

    result["status"] = "passed"
    result["failure_class"] = "none"
    result["reason"] = None
    return result


def run_command(cmd: list[str], timeout_seconds: int) -> tuple[int, str, bool]:
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
        )
        return proc.returncode, proc.stdout, False
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout if isinstance(exc.stdout, str) else ""
        return 124, output, True


def runner_execution_evidence(command: str, exit_code: int | None, output: str) -> dict[str, Any]:
    """Fail closed on runner/startup failures; exit status alone is not a test verdict."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = []
    pytest_runner = bool(tokens) and (
        Path(tokens[0]).name in {"pytest", "py.test"}
        or any(tokens[i:i + 2] == ["-m", "pytest"] for i in range(len(tokens) - 1))
    )
    if pytest_runner:
        rejected = {2: "collection", 3: "infrastructure", 4: "infrastructure", 5: "collection"}
        if exit_code in rejected:
            return {"executed": False, "failure_class": rejected[exit_code],
                    "reason": "pytest_non_test_exit_%s" % exit_code, "runner": "pytest"}
        # Quiet pytest still prints a terminal outcome summary. Collection counts
        # and skipped-only runs do not prove that a test body ran.
        failed = passed = errors = 0
        for line in output.splitlines():
            if not re.search(r"\bin [0-9.]+(?:s| seconds?)\b", line):
                continue
            failed += sum(int(n) for n in re.findall(r"\b(\d+) failed\b", line))
            passed += sum(int(n) for n in re.findall(r"\b(\d+) passed\b", line))
            errors += sum(int(n) for n in re.findall(r"\b(\d+) errors?\b", line))
        if errors:
            return {"executed": False, "failure_class": "collection",
                    "reason": "pytest_setup_or_collection_errors", "runner": "pytest"}
        valid = (exit_code == 1 and failed > 0) or (exit_code == 0 and passed > 0)
        return {"executed": valid,
                "failure_class": ("behavior_assertion" if exit_code == 1 else "none") if valid else "test_not_executed",
                "reason": "pytest_test_outcomes" if valid else "missing_pytest_test_outcomes", "runner": "pytest"}
    if exit_code == 0:
        return {"executed": True, "failure_class": "none", "reason": "generic_command_completed", "runner": "generic"}
    # Generic commands have no universal nonzero code meaning. A Python assertion
    # traceback is supported; other failures require an explicit runner adapter.
    assertion = "Traceback (most recent call last):" in output and bool(
        re.search(r"(?m)^AssertionError(?::.*)?$", output)
    )
    return {"executed": assertion, "failure_class": "behavior_assertion" if assertion else "test_not_executed",
            "reason": "python_assertion_traceback" if assertion else "unclassified_generic_nonzero", "runner": "generic"}


def ensure_selfcontained_image(bundle_dir: Path) -> dict[str, Any]:
    manifest = read_json(bundle_dir / "runtime_manifest.json")
    spec = manifest.get("selfcontained_image")
    if not isinstance(spec, dict) or spec.get("schema") != "openswe-selfcontained-image-v1":
        raise ValueError("missing or invalid selfcontained image contract")
    relative = Path(spec.get("archive", ""))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("unsafe image archive path")
    archive = bundle_dir / relative
    if archive.is_symlink() or not archive.is_file() or not archive.resolve().is_relative_to(bundle_dir.resolve()):
        raise ValueError("image archive must be an internal regular file")
    if not re.fullmatch(r"[0-9a-f]{64}", str(spec.get("archive_sha256", ""))) or sha256_file(archive) != spec["archive_sha256"]:
        raise ValueError("image archive checksum mismatch")
    image_id = spec.get("image_id", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("invalid exact image ID")
    # Bind the exact image to this archive, never to a pre-existing daemon cache.
    import tarfile
    with tarfile.open(archive, "r:*") as saved:
        members = saved.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive members")
        manifest_member = saved.getmember("manifest.json")
        if not manifest_member.isfile() or manifest_member.size > 1024 * 1024:
            raise ValueError("invalid docker save manifest")
        images = json.load(saved.extractfile(manifest_member))
        if len(images) != 1:
            raise ValueError("expected exactly one saved image")
        for layer in images[0].get("Layers", []):
            if not saved.getmember(layer).isfile():
                raise ValueError("image layer payload missing from archive")
        config_member = saved.getmember(images[0]["Config"])
        if not config_member.isfile() or config_member.size > 16 * 1024 * 1024:
            raise ValueError("invalid image config")
        config_bytes = saved.extractfile(config_member).read()
        if "sha256:" + hashlib.sha256(config_bytes).hexdigest() != image_id:
            raise ValueError("archive config does not match declared image ID")
    rc, output, timed_out = run_command(["docker", "load", "-i", str(archive)], 600)
    if rc or timed_out:
        raise ValueError("offline image load failed: " + output[-1000:])
    rc, output, timed_out = run_command(["docker", "image", "inspect", image_id], 30)
    if rc or timed_out:
        raise ValueError("loaded image identity unavailable")
    actual = json.loads(output)[0]
    if actual["Id"] != image_id or actual["Os"] != spec.get("os") or actual["Architecture"] != spec.get("architecture"):
        raise ValueError("loaded image identity/platform mismatch")
    return {"status": "passed", "image_id": image_id, "archive_sha256": spec["archive_sha256"], "external_conda_used": False}


def docker_run_mounted_eval(
    *,
    bundle_dir: Path,
    task_id: str,
    mode: str,
    image: str,
    conda_root: Path | None,
    run_root: Path,
    timeout_seconds: int,
    network: str,
    conda_read_only: bool,
    expected_command_sha256: str,
    expected_command: str = "",
) -> dict[str, Any]:
    run_id = f"{int(time.time() * 1000)}_{safe_name(mode)}"
    run_dir = run_root / safe_name(task_id) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    container_name = docker_tag(f"openswe-{task_id}-{mode}-{int(time.time() * 1000)}")
    mounts = [f"{bundle_dir.resolve()}:/bundle:ro", f"{run_dir.resolve()}:/work"]
    if conda_root is not None:
        mounts.insert(0, f"{conda_root.resolve()}:{CONTAINER_CONDA_ROOT}" + (":ro" if conda_read_only else ""))
    cmd = ["docker", "run", "--rm", "--pull", "never", "--name", container_name]
    if conda_root is None or conda_root.resolve().is_relative_to(bundle_dir.resolve()):
        network = "none"
        cmd.extend(["-e", "PYTHONNOUSERSITE=1", "-e", "HOME=/work/home", "-e", "XDG_CACHE_HOME=/work/cache"])
    if network:
        cmd.extend(["--network", network])
    cmd.extend(["-e", f"OPENSWE_MODE={mode}"])
    for mount in mounts:
        cmd.extend(["-v", mount])
    cmd.extend(["--entrypoint", "bash", image, "/bundle/run_mounted_eval.sh"])

    start = time.time()
    returncode, output, timed_out = run_command(cmd, timeout_seconds)
    if timed_out:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    openswe_code = extract_openswe_exit_code(output)
    observed_command_sha256 = extract_last_marker(output, "OPENSWE_TEST_COMMAND_SHA256")
    test_started = extract_last_marker(output, "OPENSWE_TEST_STARTED") == "1"
    test_finished = extract_last_marker(output, "OPENSWE_TEST_FINISHED") == "1"
    command_matches = bool(expected_command_sha256) and observed_command_sha256 == expected_command_sha256
    patch_failed = bool(PATCH_ERROR_RE.search(output))
    collection_failed = bool(COLLECTION_ERROR_RE.search(output))
    environment_failed = bool(ENVIRONMENT_ERROR_RE.search(output))
    infrastructure_failed = returncode != 0 or bool(INFRA_ERROR_RE.search(output))
    runner_evidence = runner_execution_evidence(expected_command, openswe_code, output)
    if timed_out:
        failure_class = "candidate_timeout" if test_started else "infra_timeout"
    elif patch_failed:
        failure_class = "patch_apply"
    elif infrastructure_failed:
        failure_class = "infrastructure"
    elif environment_failed:
        failure_class = "environment"
    elif collection_failed:
        failure_class = "collection"
    elif not test_started or not test_finished or not command_matches or openswe_code is None:
        failure_class = "test_not_executed"
    else:
        failure_class = runner_evidence["failure_class"]
    test_executed = (
        not timed_out
        and not patch_failed
        and not infrastructure_failed
        and not environment_failed
        and not collection_failed
        and test_started
        and test_finished
        and command_matches
        and openswe_code is not None
        and runner_evidence["executed"]
    )
    collected_counts = [int(value) for value in re.findall(r"collected\s+(\d+)\s+items?", output, re.IGNORECASE)]
    return {
        "mode": mode,
        "returncode": returncode,
        "timeout": timed_out,
        "duration_seconds": round(time.time() - start, 3),
        "openswe_exit_code": openswe_code,
        "passed": test_executed and openswe_code == 0 and failure_class == "none",
        "failure_class": failure_class,
        "infra_status": "infra_requeue" if failure_class in {"infrastructure", "infra_timeout"} else "ok",
        "patch_apply_failed": patch_failed,
        "collection_failed": collection_failed,
        "environment_failed": environment_failed,
        "test_started": test_started,
        "test_finished": test_finished,
        "test_executed": test_executed,
        "expected_test_command_sha256": expected_command_sha256,
        "observed_test_command_sha256": observed_command_sha256,
        "test_command_matches": command_matches,
        "collection_completed": test_executed,
        "runner_evidence": runner_evidence,
        "collected_count": collected_counts[-1] if collected_counts else None,
        "stdout_tail": "\n".join(output.splitlines()[-200:]),
        "run_dir": str(run_dir),
        "base_image": image,
        "mounts": mounts,
        "docker_command": cmd,
    }


def strict_gold_ok(gold: dict[str, Any]) -> bool:
    return (
        gold.get("patch_preflight_status") == "passed"
        and gold.get("infra_status") == "ok"
        and gold.get("timeout") is False
        and gold.get("test_executed") is True
        and gold.get("test_command_matches") is True
        and gold.get("failure_class") == "none"
        and gold.get("openswe_exit_code") == 0
        and gold.get("passed") is True
    )


def strict_testonly_red(testonly: dict[str, Any]) -> bool:
    return (
        testonly.get("patch_preflight_status") == "passed"
        and testonly.get("infra_status") == "ok"
        and testonly.get("timeout") is False
        and testonly.get("test_executed") is True
        and testonly.get("test_command_matches") is True
        and testonly.get("failure_class") == "behavior_assertion"
        and isinstance(testonly.get("openswe_exit_code"), int)
        and testonly.get("openswe_exit_code") != 0
        and testonly.get("passed") is False
    )


def verify_one_task(args: argparse.Namespace, task_id: str) -> dict[str, Any]:
    bundle_dir = args.bundle_root / safe_name(task_id)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if not bundle_dir.exists():
        return {
            "task_id": task_id,
            "ok": False,
            "mode": args.mode,
            "stage": "bundle_lookup",
            "error": f"missing bundle directory: {bundle_dir}",
            "started_at": started_at,
        }

    try:
        task: dict[str, Any]
        # New bundles seal their runnable scripts. Regenerating them here would
        # invalidate the delivered payload before its integrity check.
        embedded_contract = embedded_repo_contract_declared(bundle_dir)
        if args.regenerate_scripts and not embedded_contract:
            task = regenerate_mounted_scripts(bundle_dir)
        else:
            task = read_json(bundle_dir / "task.json")
        required = [
            "repo",
            "task.json",
            "metadata.json",
            "gold_patch.diff",
            "test_patch.diff",
            "run_mounted_eval.sh",
            "eval_testonly_mounted.sh",
            "eval_gold_mounted.sh",
        ]
        missing = [name for name in required if not (bundle_dir / name).exists()]
        if missing:
            return {
                "task_id": task_id,
                "ok": False,
                "mode": args.mode,
                "stage": "mounted_prepare",
                "missing": missing,
                "bundle_dir": str(bundle_dir),
                "started_at": started_at,
            }

        payload: dict[str, Any] = {
            "task_id": task_id,
            "mode": args.mode,
            "bundle_dir": str(bundle_dir),
            "started_at": started_at,
            "image": args.image,
            "conda_root": str(args.conda_root),
            "network": args.network,
            "seed_repo_root": str(args.seed_repo_root) if args.seed_repo_root else None,
        }
        payload["quality_gate"] = quality_gate_result(bundle_dir, task)
        if not payload["quality_gate"]["ok"]:
            payload["ok"] = False
            payload["harvest_eligible"] = False
            payload["stage"] = "quality_gate"
            payload["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            return payload

        expected_command_sha256 = str(task.get("strict_eval_command_sha256") or "")
        if not expected_command_sha256:
            payload["ok"] = False
            payload["harvest_eligible"] = False
            payload["stage"] = "test_command_proof"
            payload["error"] = "missing strict_eval_command_sha256"
            payload["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            return payload
        if not args.regenerate_scripts or embedded_contract:
            payload["command_proof"] = validate_existing_command_proof(bundle_dir, expected_command_sha256)

        payload["repo_identity"] = verify_repo_identity(bundle_dir, task, args.seed_repo_root)
        if payload["repo_identity"]["status"] != "passed":
            payload["ok"] = False
            payload["harvest_eligible"] = False
            payload["stage"] = payload["repo_identity"]["status"]
            payload["failure_class"] = payload["repo_identity"]["failure_class"]
            payload["counts_as_swe_attempt"] = False
            payload["counts_as_behavior_failure"] = False
            payload["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            return payload

        runtime = read_json(bundle_dir / "runtime_manifest.json") if (bundle_dir / "runtime_manifest.json").exists() else {}
        image_only = "selfcontained_image" in runtime or getattr(args, "require_selfcontained_image", False) or getattr(args, "require_bundle_local_env", False)
        if getattr(args, "require_bundle_local_env", False) and runtime.get("environment", {}).get("delivery") != "bundle_local_mount":
            raise ValueError("bundle-local mounted environment is required")
        selected_image, selected_conda = args.image, args.conda_root
        if image_only:
            if args.network != "none":
                raise ValueError("selfcontained verification requires network none")
            if payload["repo_identity"].get("external_seed_used"):
                raise ValueError("selfcontained verification forbids external seed")
            payload["selfcontained_image"] = ensure_selfcontained_image(bundle_dir)
            selected_image = payload["selfcontained_image"]["image_id"]
            selected_conda = None
            if runtime.get("environment", {}).get("delivery") == "bundle_local_mount":
                kit_files = read_json(bundle_dir / "runtime/conversion.json").get("validation_kit_files", {})
                required_kit = {"verify_mounted.py"}
                if runtime.get("repository") == "python/mypy": required_kit.add("source_origin_helper.py")
                if not required_kit.issubset(kit_files): raise ValueError("missing bound kit files")
                for filename, expected in kit_files.items():
                    if Path(filename).name != filename or sha256_file(Path(__file__).parent / filename) != expected:
                        raise ValueError("bound validation kit checksum mismatch: " + filename)
                payload["validation_kit_identity"] = {"status": "passed", "files": kit_files}
                relative_conda = Path(runtime.get("bundle_conda_root", ""))
                if relative_conda.is_absolute() or ".." in relative_conda.parts or not relative_conda.parts:
                    raise ValueError("unsafe bundled conda path")
                selected_conda = bundle_dir / relative_conda
                if selected_conda.is_symlink() or not selected_conda.is_dir() or not selected_conda.resolve().is_relative_to(bundle_dir.resolve()):
                    raise ValueError("bundled conda must be an internal directory")
                payload["bundle_local_environment"] = {"status": "passed", "relative_path": str(relative_conda), "external_conda_used": False}
            payload.update(image=selected_image, conda_root=None, seed_repo_root=None)
            if runtime.get("repository") == "python/mypy" or task.get("repo") == "python/mypy":
                from source_origin_helper import prove_mypy_source_origin
                payload["source_origin"] = prove_mypy_source_origin(bundle_dir, selected_image, runtime["selfcontained_image"]["environment_prefix"], conda_root=selected_conda)
                if payload["source_origin"]["status"] != "passed":
                    payload.update(ok=False, harvest_eligible=False, stage="source_origin", failure_class="infrastructure", counts_as_swe_attempt=False, counts_as_behavior_failure=False)
                    return payload

        payload["patch_preflight"] = {}
        preflight_modes = ["testonly", "gold"] if args.mode == "redgreen" else [args.mode]
        for preflight_mode in preflight_modes:
            preflight_result = patch_sequence_preflight(bundle_dir, task, preflight_mode, payload["repo_identity"])
            payload["patch_preflight"][preflight_mode] = preflight_result
            if preflight_result["status"] != "passed":
                payload["ok"] = False
                payload["harvest_eligible"] = False
                payload["stage"] = "patch_preflight"
                payload["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                return payload

        if args.mode in {"testonly", "redgreen"}:
            payload["testonly"] = docker_run_mounted_eval(
                bundle_dir=bundle_dir,
                task_id=task_id,
                mode="testonly",
                image=selected_image,
                conda_root=selected_conda,
                run_root=args.run_root,
                timeout_seconds=args.timeout_seconds,
                network=args.network,
                conda_read_only=args.conda_read_only,
                expected_command_sha256=expected_command_sha256,
                expected_command=str(task.get("strict_eval_command") or ""),
            )
            payload["testonly"]["patch_preflight_status"] = payload["patch_preflight"]["testonly"]["status"]
        if args.mode in {"gold", "redgreen"}:
            payload["gold"] = docker_run_mounted_eval(
                bundle_dir=bundle_dir,
                task_id=task_id,
                mode="gold",
                image=selected_image,
                conda_root=selected_conda,
                run_root=args.run_root,
                timeout_seconds=args.timeout_seconds,
                network=args.network,
                conda_read_only=args.conda_read_only,
                expected_command_sha256=expected_command_sha256,
                expected_command=str(task.get("strict_eval_command") or ""),
            )
            payload["gold"]["patch_preflight_status"] = payload["patch_preflight"]["gold"]["status"]
        if args.mode == "redgreen":
            payload["strict_testonly_ok"] = strict_testonly_red(payload["testonly"])
            payload["strict_gold_ok"] = strict_gold_ok(payload["gold"])
            payload["ok"] = (
                payload["quality_gate"]["ok"]
                and payload["strict_testonly_ok"]
                and payload["strict_gold_ok"]
            )
            payload["harvest_eligible"] = payload["ok"]
        elif args.mode == "gold":
            payload["strict_gold_ok"] = strict_gold_ok(payload["gold"])
            payload["ok"] = payload["quality_gate"]["ok"] and payload["strict_gold_ok"]
            payload["harvest_eligible"] = False
        else:
            payload["strict_testonly_ok"] = strict_testonly_red(payload["testonly"])
            payload["ok"] = payload["quality_gate"]["ok"] and payload["strict_testonly_ok"]
            payload["harvest_eligible"] = False
        payload["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        return payload
    except GeneratorContractError as exc:
        return {
            "task_id": task_id,
            "ok": False,
            "harvest_eligible": False,
            "mode": args.mode,
            "stage": "generator_contract",
            "failure_class": "generator_contract",
            "error": str(exc),
            "bundle_dir": str(bundle_dir),
            "started_at": started_at,
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
    except Exception as exc:
        return {
            "task_id": task_id,
            "ok": False,
            "mode": args.mode,
            "stage": "exception",
            "error": repr(exc),
            "bundle_dir": str(bundle_dir),
            "started_at": started_at,
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }


def result_path(results_dir: Path, task_id: str, mode: str) -> Path:
    return results_dir / f"{safe_name(task_id)}.{safe_name(mode)}.json"


def preflight(args: argparse.Namespace) -> None:
    if shutil.which("docker") is None:
        raise SystemExit("docker command not found")
    if shutil.which("git") is None:
        raise SystemExit("git command not found")
    if not args.bundle_root.exists():
        raise SystemExit(f"bundle root does not exist: {args.bundle_root}")
    if not (getattr(args, "require_selfcontained_image", False) or getattr(args, "require_bundle_local_env", False)) and not args.conda_root.exists():
        raise SystemExit(
            "conda dependency root does not exist: "
            f"{args.conda_root}\nSet OPENSWE_CONDA_ROOT or pass --conda-root."
        )
    args.results_dir.mkdir(parents=True, exist_ok=True)
    args.run_root.mkdir(parents=True, exist_ok=True)


def read_ids(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"ids file does not exist: {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def command_one(args: argparse.Namespace) -> int:
    preflight(args)
    result = verify_one_task(args, args.task_id)
    out = args.output or result_path(args.results_dir, args.task_id, args.mode)
    write_json(out, result)
    status = "PASS" if result.get("ok") else "FAIL"
    print(f"{status} task_id={args.task_id} mode={args.mode} result={out}")
    return 0 if result.get("ok") else 1


def command_all(args: argparse.Namespace) -> int:
    preflight(args)
    ids = read_ids(args.ids_file)
    started = time.time()
    rows: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_to_id = {pool.submit(verify_one_task, args, task_id): task_id for task_id in ids}
        for future in concurrent.futures.as_completed(future_to_id):
            task_id = future_to_id[future]
            result = future.result()
            rows.append(result)
            out = result_path(args.results_dir, task_id, args.mode)
            write_json(out, result)
            status = "PASS" if result.get("ok") else "FAIL"
            print(f"{status} task_id={task_id} mode={args.mode} result={out}", flush=True)

    rows.sort(key=lambda row: str(row.get("task_id") or ""))
    accepted = [str(row["task_id"]) for row in rows if row.get("ok")]
    failed = [str(row["task_id"]) for row in rows if not row.get("ok")]
    summary = {
        "mode": args.mode,
        "ids_file": str(args.ids_file),
        "total": len(rows),
        "accepted": len(accepted),
        "failed": len(failed),
        "accepted_ids": accepted,
        "failed_ids": failed,
        "workers": args.workers,
        "timeout_seconds": args.timeout_seconds,
        "image": args.image,
        "conda_root": str(args.conda_root),
        "bundle_root": str(args.bundle_root),
        "results_dir": str(args.results_dir),
        "run_root": str(args.run_root),
        "network": args.network,
        "seed_repo_root": str(args.seed_repo_root) if args.seed_repo_root else None,
        "wall_seconds": round(time.time() - started, 3),
    }
    write_json(args.results_dir / f"summary.{safe_name(args.mode)}.json", summary)
    tsv = args.results_dir / f"summary.{safe_name(args.mode)}.tsv"
    with tsv.open("w", encoding="utf-8") as handle:
        handle.write("task_id\tok\ttestonly_exit\tgold_exit\ttestonly_timeout\tgold_timeout\tresult_file\n")
        for row in rows:
            testonly = row.get("testonly") or {}
            gold = row.get("gold") or {}
            handle.write(
                "\t".join(
                    [
                        str(row.get("task_id") or ""),
                        str(bool(row.get("ok"))).lower(),
                        str(testonly.get("openswe_exit_code", "")),
                        str(gold.get("openswe_exit_code", "")),
                        str(testonly.get("timeout", "")),
                        str(gold.get("timeout", "")),
                        str(result_path(args.results_dir, str(row.get("task_id") or ""), args.mode)),
                    ]
                )
                + "\n"
            )
    print(
        f"SUMMARY mode={args.mode} total={len(rows)} accepted={len(accepted)} "
        f"failed={len(failed)} summary={args.results_dir / f'summary.{safe_name(args.mode)}.json'}"
    )
    return 0 if not failed else 1


def default_delivery_root() -> Path:
    env_root = os.environ.get("OPENSWE_DELIVERY_ROOT")
    if env_root:
        return Path(env_root).resolve()
    kit_root = Path(__file__).resolve().parents[1]
    if kit_root.name in {"validation_kit", "verification_kit", "acceptance_kit"}:
        return kit_root.parent.resolve()
    return kit_root.resolve()


def resolve_common_args(args: argparse.Namespace) -> argparse.Namespace:
    delivery_root = Path(args.delivery_root or default_delivery_root()).resolve()
    args.delivery_root = delivery_root
    args.bundle_root = Path(args.bundle_root or os.environ.get("OPENSWE_BUNDLE_ROOT", delivery_root / "bundles")).resolve()
    conda_default = os.environ.get(
        "OPENSWE_CONDA_ROOT",
        os.environ.get("OPENSWE_CONDA_BATCH_ROOT", str(delivery_root / "python_conda_batch")),
    )
    args.conda_root = Path(args.conda_root or conda_default).resolve()
    args.image = args.image or os.environ.get("OPENSWE_IMAGE", "swe-python-conda-runner:base-multilang-20260909")
    args.results_dir = Path(args.results_dir or os.environ.get("OPENSWE_RESULTS_DIR", delivery_root / "results")).resolve()
    args.run_root = Path(args.run_root or os.environ.get("OPENSWE_RUN_ROOT", args.results_dir / "runs")).resolve()
    seed_repo_default = args.seed_repo_root or os.environ.get("OPENSWE_SEED_REPO_ROOT")
    args.seed_repo_root = Path(seed_repo_default).resolve() if seed_repo_default else None
    args.timeout_seconds = int(args.timeout_seconds or os.environ.get("OPENSWE_TIMEOUT_SECONDS", "900"))
    args.network = args.network if args.network is not None else os.environ.get("OPENSWE_DOCKER_NETWORK", "none")
    args.network = "" if args.network in {"", "default", "host-default"} else args.network
    args.conda_read_only = not args.conda_writable and env_bool("OPENSWE_CONDA_READ_ONLY", True)
    args.regenerate_scripts = not args.no_regenerate_scripts
    return args


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--require-bundle-local-env", action="store_true", help="Require sealed per-bundle environment mounted into an unchanged base image.")
    parser.add_argument("--require-selfcontained-image", action="store_true", help="Require offline image archive inside each bundle; no external dependencies.")
    parser.add_argument("--delivery-root", help="Delivery folder root. Defaults to this script's parent directory.")
    parser.add_argument("--bundle-root", help="Bundle directory. Defaults to $OPENSWE_DELIVERY_ROOT/bundles.")
    parser.add_argument("--conda-root", help="Host conda dependency root. Defaults to $OPENSWE_DELIVERY_ROOT/python_conda_batch.")
    parser.add_argument("--image", help="Docker runtime image. Defaults to swe-python-conda-runner:mounted-slim-20260819-v2.")
    parser.add_argument("--results-dir", help="Result directory. Defaults to $OPENSWE_DELIVERY_ROOT/results.")
    parser.add_argument("--run-root", help="Writable run directory mounted as /work. Defaults to results/runs.")
    parser.add_argument(
        "--seed-repo-root",
        help="Read-only seed repositories used to attest archive bundles at the exact base commit.",
    )
    parser.add_argument("--timeout-seconds", type=int, help="Timeout per Docker phase. Defaults to 900.")
    parser.add_argument("--network", help="Docker network value. Defaults to none. Use 'default' for Docker default.")
    parser.add_argument("--conda-writable", action="store_true", help="Mount conda root read-write instead of read-only.")
    parser.add_argument("--no-regenerate-scripts", action="store_true", help="Use existing mounted scripts without rewriting from task.json.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    one = subparsers.add_parser("one", help="Verify one task.")
    add_common(one)
    one.add_argument("--task-id", required=True)
    one.add_argument("--mode", choices=["gold", "testonly", "redgreen"], default="redgreen")
    one.add_argument("--output", type=Path, help="Optional JSON output path.")
    one.set_defaults(func=command_one)

    all_parser = subparsers.add_parser("all", help="Verify tasks from an ids file.")
    add_common(all_parser)
    all_parser.add_argument("--ids-file", type=Path, help="IDs file. Defaults to accepted_swe_ids_latest.txt.")
    all_parser.add_argument("--mode", choices=["gold", "testonly", "redgreen"], default="redgreen")
    all_parser.add_argument("--workers", type=int, default=int(os.environ.get("OPENSWE_WORKERS", "4")))
    all_parser.set_defaults(func=command_all)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args = resolve_common_args(args)
    if args.command == "all" and args.ids_file is None:
        args.ids_file = args.delivery_root / "accepted_swe_ids_latest.txt"
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
