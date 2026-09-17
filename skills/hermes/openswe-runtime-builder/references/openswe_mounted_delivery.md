# OpenSWE Mounted Delivery

For Python mounted production, apply [python-bundle-local-delivery.md](python-bundle-local-delivery.md). Shared conda/seed paths in build examples are staging caches, never final runtime dependencies. Each SWE owns its environment, source/Git, data and local base archive; only the base runtime and version-bound validation kit are shared. Explicit image-only requests and other-language adapters remain separate.


Use this reference when the user asks to prepare, clean, validate, package, or upload a mounted OpenSWE delivery package such as `delivery_2000`.

This is specifically the mounted SWE delivery method: one base image plus mounted bundles, copied dependency environments/caches, validation kit, configs, metadata, and problem statements. Do not confuse it with the future pure-image delivery mode, where each SWE or task group may be delivered as Docker images without host-mounted dependency or bundle inputs.

For Go/C/C++ or language-partitioned deliveries, read `openswe_multilang_delivery.md` as well. That reference extends this one with canonical language directories, bundle ownership rules, and the unified multi-language validation kit.

## Delivery Shape

A clean mounted delivery root should be self-contained and path-independent:

```text
README.md
ids.txt
accepted_swe_ids_latest.txt
manifest.jsonl
accepted_swe_manifest_latest.jsonl
dataset.jsonl
manifest_summary.json
failed_swe_ids_latest.txt
failed_swe_manifest_latest.jsonl
bundles/
configs/
problem_statements/
bundles/<instance_id>/env/
bundles/<instance_id>/base_image.tar
images/  # optional aggregate convenience; not required by an isolated Python SWE
scripts/
validation_kit/
```

For multi-language delivery, use the canonical `bundles/c/<id>`, `bundles/c++/<id>`, and `bundles/golang/<id>` tree plus root-level ledgers that aggregate all accepted IDs. Older `<language>/bundles/<id>` trees are legacy inputs, not the preferred public contract.

Do not keep process artifacts in the final delivery root. Move `results/`, `validation_runs/`, logs, backups, temporary staging files, and `__pycache__/` to a sibling process archive if audit retention is needed.

## Metadata Contract

Each SWE must have path-independent metadata:

```text
bundles/<instance_id>/metadata.json
```

Required fields:

```json
{
  "instance_id": "stepfun_1000460",
  "repo": "spacetelescope/gwcs",
  "repo_url": "https://github.com/spacetelescope/gwcs.git",
  "base_commit": "...",
  "patch": "...",
  "problem_statement": "...",
  "image": "swe-python-conda-runner:base-multilang-20260909"
}
```

Rules:

- `patch` is the gold patch, normally read from `task.json` and cross-checked with `gold_patch.diff`.
- `problem_statement` comes from `task.json`.
- For this mounted delivery format, active metadata/config/manifest image values should use the delivered base image tag, such as `swe-python-conda-runner:base-multilang-20260909` for Python or `swe-python-conda-runner:base-gocpp-YYYYMMDD` for Go/C/C++ deliveries, unless the user explicitly asks otherwise.
- User-facing metadata, configs, manifests, README, and scripts must not hardcode producer paths such as `/data/huron`, `/data/lwj`, or `/Users/huron`.

`configs/<instance_id>.json` should repeat the key task fields and contain only relative paths.

## Build And Cleanup

1. Select accepted verified ids from production manifests without mutating production.
2. Copy only needed bundles, configs, problem statements, validation kit, base image tar, and dependency envs/caches into the delivery root.
3. If selected ids lack envs, remove those ids from the delivery and replace them with other verified ids only when replacements pass every gate; otherwise report the shortfall without forcing the requested count.
4. Rewrite metadata/config/manifest files to the delivery schema.
5. Move process files outside the delivery root.
6. Write an end-user README in Chinese for Chinese users, covering directory structure, metadata fields, image loading, validation, usage, and path independence.
7. Run strict red/green and disconnected relocation validation for every Python delivery candidate, with temporary results outside the clean root and sealed acceptance proof retained per SWE.

Minimum audits:

```bash
ROOT=/path/to/delivery_2000
wc -l "$ROOT/ids.txt" "$ROOT/manifest.jsonl" "$ROOT/dataset.jsonl" "$ROOT/accepted_swe_manifest_latest.jsonl"
find "$ROOT/bundles" -mindepth 1 -maxdepth 1 -type d | wc -l
find "$ROOT/configs" -mindepth 1 -maxdepth 1 -name '*.json' -type f | wc -l
find "$ROOT/bundles" -mindepth 2 -maxdepth 2 -name metadata.json -type f | wc -l
grep -RInE '/data/huron|/data/lwj|/Users/huron' \
  "$ROOT/README.md" "$ROOT/scripts" "$ROOT/configs" \
  "$ROOT/manifest.jsonl" "$ROOT/accepted_swe_manifest_latest.jsonl" \
  "$ROOT/bundles"/*/metadata.json || true
find "$ROOT" -maxdepth 1 \( -name results -o -name validation_runs -o -name '*.log' -o -name '*.bak' -o -name '*_tmp' \) -print
```

Mandatory verifier quality gate before user handoff:

```bash
# WORKSPACE points to a checkout that contains openswe_gair_runtime/.
python3 "$WORKSPACE/openswe_gair_runtime/scripts/audit_mounted_delivery_gate.py" \
  --delivery-root "$ROOT" \
  --image swe-python-conda-runner:base-multilang-20260909 \
  --run-redgreen \
  --workers 8 \
  --timeout-seconds 900 \
  --network none \
  --strict
```

The gate writes `audit/mounted_delivery_gate_<timestamp>.json` under the
delivery root unless `--report` is provided. A delivery is not ready if the gate
reports any of the following:

- `static_marker_suspect`: `test_patch.diff` or mounted eval scripts contain
  obvious gold-source marker oracle signals such as `ORACLE_STATIC_FAIL`,
  `openswe_oracle_test.py`, `expected_added`, `missing marker`, or tests that
  read repository source files and assert exact snippets introduced by the gold
  patch.
- `user_visible_external_path_leak`: README, manifests, configs, scripts,
  validation kit, bundle metadata, task JSON, patches, or mounted eval scripts
  contain producer paths such as `/data/huron`, `/data/lwj`, `/Users/huron`, or
  `/workspace`.
- `conda_external_path_leak`: copied conda env entrypoints or metadata still
  contain producer paths, especially old shebangs.
- `redgreen_failed`: delivery-local red/green does not show every selected SWE
  with nonzero `OPENSWE_EXIT_CODE` on `testonly` and `OPENSWE_EXIT_CODE=0` on
  `gold`.

Absence of source marker signals is only a first-pass quality signal. For
high-risk tasks, add a human or scripted provenance audit against upstream PR
tests or trajectory evidence before shipping.

## Two-Layer Acceptance

Use this two-layer process for all repaired bundles and mounted deliveries:

1. Machine gate over 100% of candidates. Run the canonical project gate script
   to produce pass, suspicious, and reject queues. The gate must include static
   marker scan, external path scan, conda path scan, and strict delivery-local
   red/green. It is intentionally high-recall and may produce false positives.
2. Semantic review. Send every suspicious or rejected-by-filter SWE to a
   subagent/human reviewer. The reviewer should classify it as true
   static-source oracle, path-dependent verifier, metadata/test mismatch,
   benign false positive, or repairable behavior test. Review every reconstructed Python verifier, including machine-passing items. For other languages, retain at least a 5% passing-sample trajectory/PR audit.

Operational rules:

- Do not ship a SWE merely because it passed red/green if its verifier is a
  gold-source marker oracle or path-dependent.
- Do not discard a SWE merely because the machine gate flagged it; first use
  semantic review unless the bad signal is explicit and unambiguous.
- Confirmed false positives should update the gate rule set and be recorded in
  the audit report.
- Confirmed verifier bugs should go to repair/quarantine. Only repaired SWE
  that pass machine gate again can return to the delivery pool.
- The final delivery audit must include the machine gate report path, the
  suspicious/reject review report, the all-Python semantic review report (or other-language passing-sample report), and final
  accepted/replaced ID counts.

## Validation

Use the delivery-local wrapper:

```bash
cd /path/to/delivery_2000
bash scripts/load_base_image.sh
python3 scripts/validate_delivery.py --ids stepfun_1000460 --mode redgreen
python3 scripts/validate_delivery.py --all --workers 8 --mode redgreen
```

The wrapper should resolve the delivery root from its own path, default to the delivered base image, default dependency roots/caches from inside the delivery when applicable, and support `--results-dir`/`--run-root` so verification output can be written outside the clean delivery root.

For multi-language deliveries, use the nested-layout-aware validator shipped with the artifact:

```bash
cd /path/to/multilang_delivery
./scripts/load_base_image.sh
python3 scripts/validate_delivery.py \
  --delivery-root . \
  --report /path/outside-delivery/delivery_gate.json \
  --results-dir /path/outside-delivery/results \
  --workers 4 --timeout-seconds 1800 --run-redgreen --strict
```

## TOS/rclone Upload

For large mounted deliveries, do not upload the expanded directory tree to object storage. Copied conda environments can produce tens of millions of objects. Package and upload an archive instead:

```text
lwjtos:tos-bjml-scpprd/liangxiuliang/swe_20260824/
  delivery_2000.tar.zst
  delivery_2000.sha256
  upload_manifest.json
```

Use `rclone copyto`, not `rclone sync`, for shared buckets.

Object storage cannot unzip archives in place. To expose an expanded tree remotely, a compute node must download/unpack and then upload each file, which is usually not appropriate for conda-heavy mounted deliveries.

Packaging shape:

```bash
ROOT=/path/to/delivery_2000
DEST_PREFIX='lwjtos:tos-bjml-scpprd/liangxiuliang/swe_20260824'
LOGROOT=/path/to/delivery_2000_upload_package_$(date +%Y%m%d_%H%M%S)
mkdir -p "$LOGROOT"
ARCHIVE="$LOGROOT/delivery_2000.tar.zst"
SHAFILE="$LOGROOT/delivery_2000.sha256"
MANIFEST="$LOGROOT/upload_manifest.json"

tar \
  --exclude='./results' \
  --exclude='./validation_runs' \
  --exclude='*/__pycache__' \
  -C "$(dirname "$ROOT")" \
  -I 'zstd -T0 -3 --long=27' \
  -cf "$ARCHIVE" \
  "$(basename "$ROOT")"

sha256sum "$ARCHIVE" | tee "$SHAFILE"
rclone copyto "$ARCHIVE" "$DEST_PREFIX/delivery_2000.tar.zst" \
  --transfers 1 --checkers 8 --retries 5 --low-level-retries 20 \
  --stats 30s --stats-one-line
rclone copyto "$SHAFILE" "$DEST_PREFIX/delivery_2000.sha256"
rclone copyto "$MANIFEST" "$DEST_PREFIX/upload_manifest.json"
```

Final reports should include delivery root, counts, path/image audit result, smoke result, `production_mutation=false`, upload destination, archive size, sha256, remote verification, and logs directory.
