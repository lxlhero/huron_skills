#!/usr/bin/env python3
"""Convenience wrapper for local or remote OpenSWE runtime pipeline execution."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path


DEFAULT_LOCAL_WORKSPACE = Path.cwd()
DEFAULT_REMOTE_HOST = "user@host"
DEFAULT_REMOTE_PORT = "22"
DEFAULT_REMOTE_ROOT = Path("/data/openswe")


def bool_flag(args: argparse.Namespace, name: str) -> bool:
    return bool(getattr(args, name))


def pipeline_command(
    root: Path,
    sample_json: Path,
    run_dir: Path | None,
    args: argparse.Namespace,
) -> list[str]:
    # Support both repo layouts:
    # 1) <root>/openswe_gair_runtime/scripts/build_portable_openswe_pipeline.py
    # 2) <root>/scripts/build_portable_openswe_pipeline.py
    candidate1 = root / "openswe_gair_runtime/scripts/build_portable_openswe_pipeline.py"
    candidate2 = root / "scripts/build_portable_openswe_pipeline.py"
    pipeline = candidate1 if candidate1.exists() else candidate2
    cmd = [
        "python3",
        str(pipeline),
        "--sample-json",
        str(sample_json),
        "--min-confidence",
        args.min_confidence,
        "--github-workers",
        str(args.github_workers),
        "--pip-index-url",
        args.pip_index_url,
        "--pip-trusted-host",
        args.pip_trusted_host,
    ]
    if args.materialize_missing_source:
        cmd.extend(["--materialize-missing-source", "--source-workers", str(args.source_workers)])
    if args.refresh_source_cache:
        cmd.append("--refresh-source-cache")
    if run_dir is not None:
        cmd.extend(["--run-dir", str(run_dir)])
    if args.ids:
        cmd.extend(["--ids", args.ids])
    if args.limit:
        cmd.extend(["--limit", str(args.limit)])
    if args.skip_github_recovery:
        cmd.append("--skip-github-recovery")
    if args.full:
        cmd.extend(["--run-build", "--run-mounted-verify", "--package"])
    else:
        for flag in ("run_build", "run_mounted_verify", "package", "package_dry_run"):
            if bool_flag(args, flag):
                cmd.append("--" + flag.replace("_", "-"))
    return cmd


def run_remote(cmd: list[str], args: argparse.Namespace) -> int:
    remote_cmd = " ".join(shlex.quote(part) for part in cmd)
    ssh_cmd = ["ssh", "-p", args.remote_port, args.remote_host, remote_cmd]
    return subprocess.run(ssh_cmd).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", action="store_true", help="Run through SSH on the known remote host.")
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-port", default=DEFAULT_REMOTE_PORT)
    parser.add_argument("--remote-root", type=Path, default=DEFAULT_REMOTE_ROOT)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_LOCAL_WORKSPACE)
    parser.add_argument("--sample-json", type=Path, default=None)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--ids", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-confidence", default="high", choices=["low", "medium", "high"])
    parser.add_argument("--github-workers", type=int, default=8)
    parser.add_argument("--pip-index-url", default="https://pypi.tuna.tsinghua.edu.cn/simple")
    parser.add_argument("--pip-trusted-host", default="pypi.tuna.tsinghua.edu.cn")
    parser.add_argument("--materialize-missing-source", action="store_true", default=True)
    parser.add_argument("--no-materialize-missing-source", action="store_false", dest="materialize_missing_source")
    parser.add_argument("--source-workers", type=int, default=8)
    parser.add_argument("--refresh-source-cache", action="store_true")
    parser.add_argument("--skip-github-recovery", action="store_true")
    parser.add_argument("--run-build", action="store_true")
    parser.add_argument("--run-mounted-verify", action="store_true")
    parser.add_argument("--package", action="store_true")
    parser.add_argument("--package-dry-run", action="store_true")
    parser.add_argument("--full", action="store_true", help="Run build, mounted verification, and portable packaging.")
    args = parser.parse_args()

    if args.remote:
        root = args.remote_root
        sample_json = args.sample_json or root / "sample.json"
        run_dir = args.run_dir or root / "new"
        cmd = pipeline_command(root, sample_json, run_dir, args)
        return run_remote(cmd, args)

    root = args.workspace
    sample_json = args.sample_json or root / "sample.json"
    run_dir = args.run_dir
    candidate1 = root / "openswe_gair_runtime/scripts/build_portable_openswe_pipeline.py"
    candidate2 = root / "scripts/build_portable_openswe_pipeline.py"
    pipeline = candidate1 if candidate1.exists() else candidate2
    if not pipeline.exists():
        parser.error(f"pipeline script not found: {pipeline}")
    cmd = pipeline_command(root, sample_json, run_dir, args)
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
