#!/usr/bin/env python3
"""Verifier-rehearsal gate: run the RED arm locally EXACTLY as the queue's verifier
would classify it, BEFORE dispatching to the queue. A material pack passes only if
the RED arm lands failure_class == behavior_assertion (python_assertion_traceback)
and the GREEN arm lands exit 0 with no non-assertion traceback.

Classification replicated from verify_mounted.py (generic runner path):
  - exit 0 -> ok
  - exit != 0: valid only if output contains 'Traceback (most recent call last):'
    AND a line matching ^AssertionError(:...)?$
Usage (on server):
  python3 preflight_rehearsal.py --id stepfun_XXXX --job /tmp/job_stepfun_XXXX.json
Exit 0 = REHEARSAL_PASS; nonzero with FAIL lines otherwise.
"""
import argparse, os, re, shutil, subprocess, sys, tempfile, json

def classify(output: str, exit_code: int):
    if exit_code == 0:
        return "none", "generic_command_completed"
    assertion = "Traceback (most recent call last):" in output and bool(
        re.search(r"(?m)^AssertionError(?::.*)?$", output))
    if assertion:
        return "behavior_assertion", "python_assertion_traceback"
    return "test_not_executed", "unclassified_generic_nonzero"

def run_arm(repo, env_python, test_path, with_gold, gold_path):
    cwd = os.getcwd()
    try:
        os.chdir(repo)
        if with_gold:
            r = subprocess.run(["git", "apply", gold_path], capture_output=True, text=True)
            if r.returncode != 0:
                return None, f"GOLD_APPLY_FAIL: {r.stderr[:200]}"
        env = dict(os.environ, PYTHONPATH=".")
        r = subprocess.run([env_python, test_path], capture_output=True, text=True, env=env, timeout=300)
        fc, reason = classify(r.stdout + r.stderr, r.returncode)
        return (r.returncode, fc, reason), None
    finally:
        os.chdir(cwd)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--job", required=True)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    W = "/data/huron/swe/work_20260923_hermes_mounted1"
    M = f"{W}/materials_v4/{a.id}"
    job = json.load(open(a.job))
    bundle, env_name = job.get("git_bundle"), job.get("env_name")
    env_py = f"{job.get('conda_root', W + '/python_conda_batch')}/envs/{env_name}/bin/python"
    fails = []

    if not os.path.isfile(env_py):
        print(f"FAIL: env python missing: {env_py}"); return 1
    if not os.path.isfile(bundle or ""):
        print(f"FAIL: bundle missing: {bundle}"); return 1

    td = tempfile.mkdtemp(prefix=f"rehearsal.{a.id}.")
    try:
        repo = os.path.join(td, "r")
        r = subprocess.run(["git", "clone", "-q", bundle, repo], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"FAIL: bundle clone: {r.stderr[:200]}"); return 1
        ident = f"{W}/identities_batch1/{a.id}.json"
        base = json.load(open(ident)).get("base_commit") if os.path.isfile(ident) else None
        if base:
            r = subprocess.run(["git", "checkout", "-q", base], cwd=repo, capture_output=True, text=True)
            if r.returncode != 0:
                print(f"FAIL: base checkout {base}: {r.stderr[:150]}"); return 1
        r = subprocess.run(["git", "apply", f"{M}/test_patch.diff"], cwd=repo, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"FAIL: test apply: {r.stderr[:200]}"); return 1

        red, err = run_arm(repo, env_py, "test_repro.py", False, None)
        if err: print(f"FAIL: {err}"); return 1
        rc_r, fc_r, reason_r = red
        if not (rc_r == 1 and fc_r == "behavior_assertion"):
            print(f"FAIL: RED arm rc={rc_r} class={fc_r} ({reason_r}) — verifier would REJECT (need rc=1 + AssertionError traceback)")
            return 1
        print(f"RED ok: rc=1 behavior_assertion ({reason_r})")

        # GREEN arm on a fresh clone
        repo2 = os.path.join(td, "g")
        subprocess.run(["git", "clone", "-q", bundle, repo2], capture_output=True)
        if base: subprocess.run(["git", "checkout", "-q", base], cwd=repo2, capture_output=True)
        subprocess.run(["git", "apply", f"{M}/test_patch.diff"], cwd=repo2, capture_output=True)
        green, err = run_arm(repo2, env_py, "test_repro.py", True, f"{M}/gold_patch.diff")
        if err: print(f"FAIL: {err}"); return 1
        rc_g, fc_g, reason_g = green
        if rc_g != 0:
            print(f"FAIL: GREEN arm rc={rc_g} class={fc_g} — gold does not turn test green")
            return 1
        print(f"GREEN ok: rc=0")
        print(f"REHEARSAL_PASS {a.id}")
        return 0
    finally:
        if not a.keep:
            shutil.rmtree(td, ignore_errors=True)

if __name__ == "__main__":
    sys.exit(main())
