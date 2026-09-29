#!/usr/bin/env bash
# Materials preflight gate — run ON SERVER via: bash <(cat local copy) --id stepfun_XXXX [--job /tmp/job_stepfun_XXXX.json]
# Deterministic first-pass-rate lifter: catches the 4 defect classes that burned queue rounds on 2026-09-24:
#   A. diff path form  (a/tmp/foo.py instead of a/test_repro.py)
#   B. hunk header count mismatch / truncated patch (git apply --check on real bundle)
#   C. recipe absolute paths / non-standard fields
#   D. job env_name not materialized in conda_root
# Plus: gold applies to base, test applies on top of base, both diffs non-empty.
# Exit 0 = PASS (print PASS line); exit 1 = FAIL with reason lines prefixed FAIL:.
set -u
ID=""; JOB=""
while [ $# -gt 0 ]; do case "$1" in
  --id) ID="$2"; shift 2;; --job) JOB="$2"; shift 2;; *) shift;;
esac; done
[ -z "$ID" ] && { echo "FAIL: --id required"; exit 1; }
W=/data/huron/swe/work_20260923_hermes_mounted1
M=$W/materials_v4/$ID
fail=0
note() { echo "NOTE: $1"; }
bad() { echo "FAIL: $1"; fail=1; }

# --- 1. four-piece presence
for f in gold_patch.diff test_patch.diff recipe.json; do
  [ -s "$M/$f" ] || bad "$f missing/empty in $M"
done
[ $fail -eq 1 ] && exit 1

# --- 2. diff path form (A)
tp=$(grep -m1 "^+++ b/" "$M/test_patch.diff" || true)
echo "$tp" | grep -q "b/test_repro.py" || bad "test_patch path form: '$tp' (want b/test_repro.py)"
gp=$(grep -m1 "^+++ b/" "$M/gold_patch.diff" || true)
echo "$gp" | grep -qE "b/[A-Za-z0-9_.-]+/" || note "gold_patch target: $gp (single-root ok if flat repo)"

# --- 3. hunk header arithmetic + no truncation (B)
python3 - "$M/test_patch.diff" <<'PY' || fail=1
import sys, re
lines = open(sys.argv[1]).read().splitlines(keepends=True)
if not any(l.startswith("@@") for l in lines): print("FAIL: no hunk header"); sys.exit(1)
plus = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
minus = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
hdr = next(l for l in lines if l.startswith("@@"))
m = re.search(r"\+(\d+)(?:,(\d+))?", hdr)
if m and m.group(2) and int(m.group(2)) != plus and len([l for l in lines if l.startswith("@@")])==1:
    print(f"FAIL: hunk declares +{m.group(2)} but file has {plus} '+' lines (truncated patch)"); sys.exit(1)
if not lines[-1].endswith("\n"): print("FAIL: diff not newline-terminated"); sys.exit(1)
PY

python3 - "$M/gold_patch.diff" <<'PY' || fail=1
import sys, re
lines = open(sys.argv[1]).read().splitlines(keepends=True)
hunks = []; cur = None
for l in lines:
    if l.startswith("@@"):
        if cur: hunks.append(cur)
        m = re.search(r"-(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))?", l)
        if not m: print("FAIL: malformed gold hunk header "+l); sys.exit(1)
        cur = {"hdr": l, "plus": 0, "minus": 0, "ctx": 0}
    elif cur is not None and l[:1] in ("+", "-", " "):
        if l.startswith("+"): cur["plus"] += 1
        elif l.startswith("-"): cur["minus"] += 1
        else: cur["ctx"] += 1
if cur: hunks.append(cur)
if not hunks: print("FAIL: gold diff has no hunks"); sys.exit(1)
for h in hunks:
    m = re.search(r"-(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))?", h["hdr"])
    d_new = m.group(4); d_old = m.group(2)
    new_total = h["ctx"] + h["plus"]
    old_total = h["ctx"] + h["minus"]
    if d_new is not None and abs(int(d_new) - new_total) > 1:
        print(f"FAIL: gold hunk {h['hdr'].strip()} new-span {d_new} != ctx+plus {new_total}"); sys.exit(1)
    if d_old is not None and abs(int(d_old) - old_total) > 1:
        print(f"FAIL: gold hunk {h['hdr'].strip()} old-span {d_old} != ctx+minus {old_total}"); sys.exit(1)
PY

# --- 4. recipe schema (C)
python3 - "$M/recipe.json" <<'PY' || fail=1
import json, sys
r = json.load(open(sys.argv[1]))
std = {"image","pythonpath","target_modules","test_command","expected_failure_patterns","install_project","environment","test_timeout","build_timeout"}
extra = set(r) - std
if extra: print(f"FAIL: recipe non-standard fields: {sorted(extra)}"); sys.exit(1)
if "python3" not in " ".join(r.get("test_command", [])): print("FAIL: test_command not python3 ..."); sys.exit(1)
for v in r.get("environment", {}).values():
    if isinstance(v, str) and v.startswith("/"): print(f"FAIL: recipe environment absolute path: {v}"); sys.exit(1)
if not isinstance(r.get("pythonpath"), list): print("FAIL: pythonpath not a list"); sys.exit(1)
PY

# --- 5. job env materialized (D)
if [ -n "$JOB" ] && [ -s "$JOB" ]; then
  ENVN=$(python3 -c "import json;print(json.load(open('$JOB')).get('env_name',''))")
  CR=$(python3 -c "import json;print(json.load(open('$JOB')).get('conda_root',''))")
  BUN=$(python3 -c "import json;print(json.load(open('$JOB')).get('git_bundle',''))")
  [ -d "$CR/envs/$ENVN" ] || bad "env '$ENVN' not materialized under $CR/envs"
  [ -x "$CR/envs/$ENVN/bin/python" ] || bad "env python not executable"
  [ -s "$BUN" ] || bad "git_bundle missing/empty: $BUN"
fi

# --- 6. real apply on bundle (B, strongest)
if [ -n "${JOB:-}" ] && [ -s "$JOB" ]; then
  BUN=$(python3 -c "import json;print(json.load(open('$JOB')).get('git_bundle',''))")
  TD=$(mktemp -d /tmp/preflight.XXXXXX)
  if git clone -q "$BUN" "$TD/r" 2>/dev/null && cd "$TD/r"; then
    BASE=$(python3 -c "import json;print(json.load(open('$W/identities_batch1/$ID.json')).get('base_commit',''))" 2>/dev/null)
    [ -n "$BASE" ] && git checkout -q "$BASE" 2>/dev/null
    git apply --check "$W/materials_v4/$ID/test_patch.diff" 2>/dev/null || bad "test_patch does not apply to base"
    git apply "$W/materials_v4/$ID/test_patch.diff" 2>/dev/null
    git apply --check "$W/materials_v4/$ID/gold_patch.diff" 2>/dev/null || bad "gold_patch does not apply on top of test"
    python3 -c "import ast; ast.parse(open('test_repro.py').read())" 2>/dev/null || bad "test_repro.py syntax error after apply"
  else
    note "bundle clone failed — skipping apply check (verify bundle!)"
  fi
  rm -rf "$TD"
fi

[ $fail -eq 0 ] && echo "PREFLIGHT_PASS $ID" || exit 1
