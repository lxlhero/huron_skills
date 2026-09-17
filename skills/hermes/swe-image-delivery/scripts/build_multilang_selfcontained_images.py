#!/usr/bin/env python3
"""Build and optionally push self-contained OpenSWE multi-language images.

The input is a mounted multi-language delivery with bundles under
bundles/<language>/<task_id>. Each output image embeds exactly one bundle at
/bundle and runs the bundle's run_mounted_eval.sh directly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ENTRYPOINT = """#!/usr/bin/env bash
set -u
mode="${1:-testonly}"
case "$mode" in
  describe|description|problem)
    if [ -f /problem/README.md ]; then
      cat /problem/README.md
    elif [ -f /bundle/problem_statement.txt ]; then
      cat /bundle/problem_statement.txt
    else
      echo "No problem statement found."
    fi
    exit 0
    ;;
  testonly|gold) ;;
  *)
    echo "usage: $0 [describe|testonly|gold]" >&2
    exit 64
    ;;
esac
rm -rf /work/testbed /work/go-mod /work/gopath /work/go-build /work/build /work/instance_bridge
mkdir -p /work
export OPENSWE_WORK_ROOT=/work
exec bash /bundle/run_mounted_eval.sh "$mode"
"""


def run(cmd: list[str], *, log: Path | None = None, timeout: int | None = None) -> int:
    print("+ " + " ".join(cmd), flush=True)
    if log is None:
        return subprocess.call(cmd, timeout=timeout)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as fh:
        return subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT, timeout=timeout)


def safe_tag(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return cleaned.strip(".-") or "task"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(errors="replace"))


def load_ids(delivery_root: Path, ids: str, ids_file: Path | None, limit: int) -> list[str]:
    if ids_file:
        raw = [x.strip() for x in ids_file.read_text().splitlines() if x.strip()]
    elif ids:
        raw = [x for x in re.split(r"[\s,]+", ids) if x]
    else:
        source = delivery_root / "accepted_swe_ids_latest.txt"
        if not source.exists():
            source = delivery_root / "ids.txt"
        raw = [x.strip() for x in source.read_text().splitlines() if x.strip()]
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        if item not in seen:
            result.append(item)
            seen.add(item)
        if limit and len(result) >= limit:
            break
    return result


def find_bundle(delivery_root: Path, task_id: str) -> tuple[str, Path]:
    matches = sorted((delivery_root / "bundles").glob(f"*/{task_id}"))
    if len(matches) != 1:
        raise FileNotFoundError(f"expected exactly one bundle for {task_id}, found {len(matches)}")
    return matches[0].parent.name, matches[0]


def sh_quote_for_docker(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def make_problem_readme(task_id: str, language: str, task: dict, image: str) -> str:
    repo = task.get("repo") or ""
    base_commit = task.get("base_commit") or ""
    test_command = task.get("test_command") or ""
    statement = (task.get("problem_statement") or "").rstrip()
    return f"""# OpenSWE Task {task_id}

Language: {language}
Repository: {repo}
Base commit: {base_commit}

## Problem Statement

{statement}

## Test Command

```bash
{test_command}
```

## Image Commands

```bash
docker run --rm {image} describe
docker run --rm --network none {image} testonly
docker run --rm --network none {image} gold
```
"""


def build_context(
    *,
    context: Path,
    bundle: Path,
    task_id: str,
    language: str,
    task: dict,
    base_image: str,
    image: str,
) -> None:
    if context.exists():
        shutil.rmtree(context)
    context.mkdir(parents=True)
    shutil.copytree(bundle, context / "bundle", symlinks=True)
    problem = context / "problem"
    problem.mkdir()
    (problem / "README.md").write_text(make_problem_readme(task_id, language, task, image))
    (problem / "statement.txt").write_text((task.get("problem_statement") or "").rstrip() + "\n")
    (context / "openswe-entrypoint.sh").write_text(ENTRYPOINT)

    repo = task.get("repo") or ""
    base_commit = task.get("base_commit") or ""
    statement = " ".join((task.get("problem_statement") or "").split())[:300]
    labels = [
        ("org.opencontainers.image.title", f"OpenSWE task {task_id}"),
        ("org.opencontainers.image.description", statement),
        ("openswe.task.id", task_id),
        ("openswe.language", language),
        ("openswe.repo", repo),
        ("openswe.base_commit", base_commit),
        ("openswe.problem.statement", task.get("problem_statement") or ""),
    ]
    label_separator = " \\" + "\n" + "      "
    label_text = label_separator.join(f"{k}={sh_quote_for_docker(v)}" for k, v in labels)
    dockerfile = f"""FROM {base_image}
LABEL {label_text}
COPY bundle/ /bundle/
COPY problem/ /problem/
COPY openswe-entrypoint.sh /usr/local/bin/openswe-selfcontained
RUN chmod +x /usr/local/bin/openswe-selfcontained /bundle/run_mounted_eval.sh && mkdir -p /work /input
ENV OPENSWE_WORK_ROOT=/work
ENTRYPOINT ["/usr/local/bin/openswe-selfcontained"]
CMD ["testonly"]
"""
    (context / "Dockerfile").write_text(dockerfile)


def parse_openswe_exit(log: Path) -> str:
    text = log.read_text(errors="replace") if log.exists() else ""
    matches = list(re.finditer(r"OPENSWE_EXIT_CODE=([-0-9]+)", text))
    return matches[-1].group(1) if matches else "NA"


def verify_image(image: str, task_id: str, logs: Path, timeout: int, sudo: bool) -> list[dict]:
    results: list[dict] = []
    docker = ["docker"]
    if sudo:
        docker = ["sudo", "HOME=/root", "DOCKER_CONFIG=/root/.docker", "docker"]
    for mode in ("describe", "testonly", "gold"):
        log = logs / f"{task_id}_{mode}.log"
        cmd = docker + ["run", "--rm"]
        if mode != "describe":
            cmd += ["--network", "none"]
        cmd += [image, mode]
        rc = run(["timeout", str(timeout)] + cmd, log=log)
        openswe_exit = parse_openswe_exit(log)
        if mode == "describe":
            status = "PASS" if rc == 0 and log.stat().st_size > 0 else "FAIL"
        elif mode == "testonly":
            status = "PASS" if openswe_exit not in {"NA", "0"} else "FAIL"
        else:
            status = "PASS" if openswe_exit == "0" else "FAIL"
        results.append(
            {
                "mode": mode,
                "rc": rc,
                "openswe_exit": openswe_exit,
                "status": status,
                "log": str(log),
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delivery-root", type=Path, required=True)
    parser.add_argument("--ids", default="")
    parser.add_argument("--ids-file", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--base-image", required=True)
    parser.add_argument("--image-repository", required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--sudo-docker", action="store_true")
    args = parser.parse_args()

    args.output_root.mkdir(parents=True, exist_ok=True)
    contexts = args.output_root / "contexts"
    logs = args.output_root / "logs"
    contexts.mkdir(exist_ok=True)
    logs.mkdir(exist_ok=True)

    docker = ["docker"]
    if args.sudo_docker:
        docker = ["sudo", "HOME=/root", "DOCKER_CONFIG=/root/.docker", "docker"]

    task_ids = load_ids(args.delivery_root, args.ids, args.ids_file, args.limit)
    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "delivery_root": str(args.delivery_root),
        "base_image": args.base_image,
        "image_repository": args.image_repository,
        "items": [],
    }

    pull_rc = run(docker + ["pull", args.base_image], log=logs / "base_pull.log")
    if pull_rc != 0:
        raise SystemExit(f"base image pull failed rc={pull_rc}")

    all_ok = True
    for task_id in task_ids:
        language, bundle = find_bundle(args.delivery_root, task_id)
        task = read_json(bundle / "task.json")
        tag = safe_tag(task_id)
        image = f"{args.image_repository}:{tag}"
        context = contexts / task_id
        print(f"=== {task_id} ({language}) -> {image} ===", flush=True)
        build_context(
            context=context,
            bundle=bundle,
            task_id=task_id,
            language=language,
            task=task,
            base_image=args.base_image,
            image=image,
        )
        build_log = logs / f"{task_id}_build.log"
        build_rc = run(docker + ["build", "-t", image, str(context)], log=build_log)
        item = {
            "id": task_id,
            "language": language,
            "bundle": str(bundle),
            "image": image,
            "context": str(context),
            "build_log": str(build_log),
            "build_rc": build_rc,
            "verify": [],
            "push_rc": None,
            "digest": None,
        }
        if build_rc != 0:
            all_ok = False
            summary["items"].append(item)
            continue
        if args.verify:
            item["verify"] = verify_image(image, task_id, logs, args.timeout_seconds, args.sudo_docker)
            if any(v["status"] != "PASS" for v in item["verify"]):
                all_ok = False
                summary["items"].append(item)
                continue
        if args.push:
            push_log = logs / f"{task_id}_push.log"
            push_rc = run(docker + ["push", image], log=push_log)
            item["push_rc"] = push_rc
            item["push_log"] = str(push_log)
            if push_rc != 0:
                all_ok = False
            else:
                inspect_log = logs / f"{task_id}_inspect.json"
                with inspect_log.open("w") as fh:
                    subprocess.call(docker + ["image", "inspect", image], stdout=fh, stderr=subprocess.STDOUT)
                item["inspect_log"] = str(inspect_log)
                try:
                    data = json.loads(inspect_log.read_text())[0]
                    digests = data.get("RepoDigests") or []
                    item["digest"] = next((d for d in digests if d.startswith(args.image_repository + "@")), None)
                except Exception:
                    pass
        summary["items"].append(item)

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary["ok"] = all_ok
    summary_path = args.output_root / "selfcontained_image_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False), flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
