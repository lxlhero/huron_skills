# OpenSWE Multi-Language Mounted Delivery

Use this reference when building, validating, repairing, packaging, or explaining OpenSWE-style mounted deliveries for Go, C, and C++ tasks. This extends the Python mounted delivery model without replacing it: the preferred artifact is still one shared base image plus per-SWE mounted bundles.

## Canonical Language Model

Normalize language labels before producing any files:

```text
go, golang       -> golang
c                -> c
cxx, cpp, c++    -> c++
python, py       -> python
```

For C++, use `c++` everywhere in the delivered tree and manifests unless the user explicitly asks for a different public contract. Do not deliver both `cpp/` and `c++/`; duplicate aliases create ambiguous bundle ownership and make validation harder to trust.

## Broad Candidate Recall

When high-confidence rows with ready `patch` and `test_patch` are exhausted, switch to broad trajectory recall rather than stopping the production stream. The broad pool should include SWE whose trajectory contains evidence of the target language, for example language file paths in diffs, tool calls, edits, reads, command output, or build/test commands.

Use evidence tiers:

```text
strong:    gold/test diff actually modifies target-language files
medium:    tool calls edit/write/create/open/read target-language paths
support:   commands mention target-language test/build tools or repo markers
weak:      natural language mentions the language
```

Broad recall is not acceptance. Every broad candidate must carry `language_evidence`, but only a delivery-local red/green validation pass can promote it to accepted output.

After extracting a broad candidate into an eval-ready row, run a target-language diff-path gate before Docker validation. For Go, both `patch` and `test_patch` should touch `.go`; for C, both should touch `.c`; for C++, both should touch C++-relevant source/header files such as `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh`, `.hxx`, or project-appropriate `.h`. If the extracted patches only touch Python, Java, docs, data files, fixtures, or shell-only repro wrappers, record `language_path_filter_failed` and keep the candidate out of the Docker verification lane.

If extraction finishes but still lacks either `patch` or `test_patch`, record a structural reject such as `missing_patch_or_test_patch` and preserve the raw row/logs for future recovery work. Do not spend all three repair attempts rerunning an extractor that has no additional inference path in the current producer.

If broad extraction cannot recover a usable `repo` and `base_commit`, record `missing_repo_or_base_commit` and keep the raw row/logs for future source recovery. These rows cannot be mounted, patched, or red/green validated until source identity is repaired, so they should not repeatedly consume normal repair attempts.

When widening recall directly from raw trajectory text, keep a strict production gate between "path-like text match" and "candidate worth running". Match complete extensions only: do not let `.c` match `.cs`, `.coffee`, `.css`, or `.cjs`; do not let `.go` match `.gov` or Maven-style `com.go` fragments. Exclude URL/domain false positives such as `.gov`, `.com`, `cgi/viewcontent.c`, Maven/Gradle cache paths such as `com.go`, Python `__pycache__` pseudo-files, C# `.cs` paths, Java/.NET build output, `setup.c` from Python packaging, web assets such as `webpack.c` or `vite.c`, and docs/data/fixture-only paths. If the evidence is only one of these shapes, record it as scan noise or a low-priority research item rather than appending it to the production pool.

C/C++ classification rules:

- `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh`, and `.hxx` are C++ evidence.
- `.c` is C evidence unless the same SWE has stronger C++ evidence.
- `.h` alone is ambiguous and should not decide C vs C++ by itself.
- If evidence is mixed and tied, put the SWE in a rejected or manual-review pool instead of forcing it into a delivery language directory.
- If broad recall assigned one target language but the extractor later produces a different canonical target language with concrete patch/test evidence, prefer the extractor's canonical language for validation and delivery. Record `broad_language`, `extracted_language`, and a reconciliation reason in the task metadata so the handoff remains auditable.

## Base Image Rule

Start from the existing Python runner image and layer additional native toolchains on top. The multi-language image should preserve Python and conda because future mixed-language delivery should be able to use a single mounted runner.

Minimum checks after build or load:

```bash
docker run --rm <image> python --version
docker run --rm <image> conda --version
docker run --rm <image> go version
docker run --rm <image> gcc --version
docker run --rm <image> g++ --version
docker run --rm <image> cmake --version
docker run --rm <image> make --version
docker run --rm <image> git --version
```

If a tool is intentionally absent, record the reason in the delivery manifest and do not accept SWE that require it.

## Delivery Shape

A clean multi-language mounted delivery root should be path-independent and should treat each SWE bundle as the primary unit. The canonical public layout is `bundles/<language>/<instance_id>`:

```text
verified_swe_output_by_language/
  README.md
  ids.txt
  accepted_swe_ids_latest.txt
  accepted_swe_manifest_latest.jsonl
  failed_swe_ids_latest.txt
  failed_swe_manifest_latest.jsonl
  manifest.jsonl
  dataset.jsonl
  summary.json
  images/
    <base-image>.tar
  scripts/
    load_base_image.sh
  scripts/
    load_base_image.sh
    validate_delivery.py
  bundles/
    c/<instance_id>/
    c++/<instance_id>/
    golang/<instance_id>/
```

Every accepted id must appear exactly once under one canonical language directory, and root-level ledgers must agree with the bundle count and language assignment. Treat older `<language>/bundles/<id>` trees as a legacy input layout only; do not generate new deliveries in both shapes and do not make users depend on an external normalization step.

## Bundle Contract

Each bundle directory should contain everything needed for that SWE except the shared base image and a fresh writable run directory:

```text
bundles/<language>/<instance_id>/
  task.json
  metadata.json
  gold_patch.diff
  test_patch.diff
  run_mounted_eval.sh
  run_redgreen.sh       # or an equivalent direct bundle entrypoint
  source archive/snapshot
  problem_statement.txt or problem/
  deps/                # optional, for offline language caches
```

Rules:

- `metadata.json`, `task.json`, configs, root manifests, README files, and scripts must not hardcode producer paths such as `/data/huron`, `/data/lwj`, or `/Users/huron`.
- `metadata.json.image` should point at the delivered base image tag, for example `swe-python-conda-runner:base-gocpp-YYYYMMDD`.
- The gold patch in metadata/task JSON should match `gold_patch.diff`; the test patch should match `test_patch.diff`.
- For Go, capture module caches needed for `--network none` validation under `deps/go-mod` and mount them read-only to `/work/.cache/go-mod`.
- For Go, inspect `test_patch` for standalone repro scripts by content, not filename alone. Any patched `.go` file with top-level `package main` and `func main` should run separately with `go run`, even if its filename ends in `_test.go`, unless it also contains a real Go test entrypoint. Only `_test.go` files with top-level `func TestXxx`, `func FuzzXxx`, or `func BenchmarkXxx` should drive the normal `go test` path.
- When running a standalone repro whose source filename ends in `_test.go`, copy it to a temporary sibling name that is visible to Go and does not end in `_test.go`, then remove the temporary file. Go refuses `go run *_test.go` and ignores dot/underscore-prefixed files, so a filename-only copy can still leave a false gold failure.
- A Go standalone repro may print a clear failure marker and still exit 0. It is acceptable for the standalone repro wrapper to convert only that repro's stdout/stderr markers such as `FAIL:`, `FAIL -`, `ERROR:`, `Error:`, or `Failed ` into a nonzero `OPENSWE_EXIT_CODE`, provided strict delivery-local red/green still proves `testonly` nonzero and `gold` zero.
- For `containous/yaegi` and `traefik/yaegi` only, standalone sample programs usually reproduce interpreter failures through `yaegi run <sample.go>`, not native `go run <sample.go>`. For those repos, run standalone repro files with `GO111MODULE=on go run ./cmd/yaegi run <sample.go>` while keeping true Go tests on the normal `go test` path. Do not generalize this interpreter runner to other Go repositories without observed evidence and a separate review.
- Do not apply Go standalone marker matching to `go test` output, repository build logs, CLI help text, fixtures, patch-application logs, Python, C, or C++. Do not run arbitrary non-test Go library/command files; require clear standalone repro shape and run multiple `func main` files one by one to avoid artificial duplicate-main conflicts and `_test.go` files that are really standalone repros.
- For C/C++, keep generated build directories in `/work`, not in `/bundle`, and make `run_mounted_eval.sh` robust to repeated clean runs.
- Invoke direct bundle scripts by their absolute bundle path from an unrelated current working directory during acceptance. A runner that only works after `cd` into a producer workspace is not portable.
- Mount `/bundle` read-only. A passing run must not leave compiler outputs, module caches, logs, or results inside the delivered bundle.

## Delivery-Local Path-Aware Validator

The delivery-local validator is part of the artifact, not an external producer script. It should:

- Resolve `DELIVERY_ROOT` from the script location by default.
- Discover `bundles/c/<id>`, `bundles/c++/<id>`, and `bundles/golang/<id>` without flattening or aliasing them.
- Read root `manifest.jsonl` and `accepted_swe_ids_latest.txt`.
- Support `one` and `all` scopes, `redgreen`, `testonly`, and `gold` modes, and `--language c|c++|golang`.
- Mount the bundle read-only at `/bundle`.
- Mount a fresh writable run directory at `/work`.
- Mount optional language caches, especially Go modules, read-only from the bundle.
- Record per-run `result.json`, per-id JSON results, `summary.redgreen.json`, and `summary.redgreen.tsv`.
- Default `results/` and `runs/` to a sibling process directory outside the clean delivery root.

Acceptance criteria are strict:

```text
testonly: OPENSWE_EXIT_CODE is present and nonzero
gold:     OPENSWE_EXIT_CODE is present and equals 0
timeout:  always failure
missing OPENSWE_EXIT_CODE: always failure
```

Do not accept a SWE based only on Docker's process return code.

## Manual Validation Commands

Use actual produced ids, not placeholder directories:

```bash
cd /path/to/multilang_delivery
./scripts/load_base_image.sh

python3 scripts/validate_delivery.py \
  --delivery-root . \
  --report /path/outside-delivery/delivery_gate.json \
  --results-dir /path/outside-delivery/results \
  --workers 4 \
  --timeout-seconds 1800 \
  --run-redgreen \
  --strict
```

Expected output locations:

```text
<delivery_parent>/<delivery_name>_validation_runs_<timestamp>/results/summary.redgreen.json
<delivery_parent>/<delivery_name>_validation_runs_<timestamp>/results/summary.redgreen.tsv
<delivery_parent>/<delivery_name>_validation_runs_<timestamp>/runs/<instance_id>/<run_id>/result.json
```

## Production Workflow

For a new multi-language production run:

1. Count raw candidates by normalized language before selecting.
2. If high-confidence candidate rows are exhausted, build a broad candidate pool from trajectory language-file evidence. Record evidence for each row before any build attempt.
3. Extract the requested languages into a dedicated work root such as `work_YYYYMMDD/data`.
4. Copy current project scripts into the work root and adapt them there first.
5. Build the shared multi-language base image and save its tar under `images/`.
6. Produce small smoke candidates across languages, then optimize scripts based on real failures.
7. Scale to batch production with one repair worker lane per language when possible.
8. Limit each SWE to three real failed attempts and four hours of active attempt runtime. Do not treat delayed automation review as task runtime: if an old `first_started_at + 4h` deadline fired after a quick terminal failure, or a stopped/crashed old batch left an orphan `building` event, append a `stale_timeout_requeued` history event and return the SWE to candidate/repair flow unless it already hit the real failure cap. Only the current batch's unclosed active attempt should be eligible for a real four-hour timeout.
9. For streaming throughput, shard noisy broad pools into disjoint lanes, for example multiple Go shards plus smaller C/C++ shards. Use `(language, shard_index, shard_count)` to avoid duplicate work, and keep failed-but-not-exhausted candidates behind never-tried candidates.
10. Protect concurrent lanes with locks for attempt state, source materialization, and production promotion. Source materialization must be locked per repo+commit because parallel archive extraction into the same worktree can corrupt or fail the shared seed worktree.
11. Promote only red/green verified bundles into the delivery root. In concurrent production, do not count a SWE as accepted just because the bundle exists or appears in `ids.txt`; it is accepted only after the delivery-local red/green validation passes and an accepted-ledger row is appended.
12. Install the delivery-local, nested-layout-aware loader and validator.
13. Run full acceptance through that validator with reports outside the delivery root, then audit the clean delivery root.

Patch normalization rule:

- For `git apply` failures like `already exists in working directory`, inspect added-file diff sections before treating the SWE as broken. If a `new file mode` section targets a file that already exists in the base worktree, reconstruct the section's added bytes and compare them byte-for-byte with the base file.
- Delete an added-file diff section only when the base worktree is readable, the target file already exists, and the reconstructed added content is byte-identical to the existing base file. This is a conservative no-op normalization for duplicate file creation, not a general patch repair.
- Do not apply this rule to modified files, deleted files, renames, mode-only changes, binary patches, symlinks, unreadable files, or any case with non-identical bytes. On uncertainty, leave the patch unchanged and require the normal strict red/green gate.
- This normalization may be applied to candidate `test_patch` or `gold_patch` artifacts before validation, but it must never delete worktree files or rewrite already accepted production bundles, manifests, ledgers, or latest accepted-id files.

C++ focused-test repair:

- For C++ `jbeder/yaml-cpp` only, if full CMake plus `ctest` fails with `ninja: error: 'test/prefix/lib/libgmock.a', needed by 'test/run-tests'`, treat it as an upstream test-harness dependency trap rather than immediate candidate failure.
- The approved `yaml-cpp` repair is narrow: configure with `-DYAML_CPP_BUILD_TESTS=OFF -DYAML_BUILD_SHARED_LIBS=OFF`, build only the static `yaml-cpp` library, then compile and run the `.cpp` focused repro tests introduced by the trajectory `test_patch` against `/work/build/libyaml-cpp.a`.
- Do not generalize this to other CMake C++ repositories. Disabling repository tests is allowed only when the trajectory supplies standalone focused tests and strict delivery-local red/green still proves `testonly` nonzero and `gold` zero with present `OPENSWE_EXIT_CODE` markers.
- Preserve accepted outputs append-only; this rule is for future validation and repair behavior and must not delete, rewrite, or re-harvest already accepted bundles.

Subagents can be used for language-specific repairs, but the main agent remains responsible for the global ledger, canonical paths, and final acceptance gate.

## Production Ledgers

Keep broad candidate selection, attempts, accepted output, and rejection separate. A practical layout is:

```text
production_ledger/
  candidates.jsonl
  candidate_pool_summary.json
  attempts.jsonl
  attempts_state.json
  accepted.jsonl
  rejected.jsonl
rejected_swe/
  c/<instance_id>/
  c++/<instance_id>/
  golang/<instance_id>/
```

Each attempt or terminal state should record:

```json
{
  "instance_id": "stepfun_xxx",
  "language": "golang",
  "batch_id": "batch100_broad_YYYYMMDD_HHMMSS",
  "status": "building|failed|accepted|rejected|rejected_timeout_4h|stale_timeout_requeued",
  "attempt": 2,
  "max_attempts": 3,
  "max_wall_seconds": 14400,
  "deadline_at": 1780000000,
  "repo": "owner/repo",
  "error": "short failure reason",
  "bundle_path": "bundles/golang/stepfun_xxx",
  "validation_summary": "sibling validation result path"
}
```

The clean delivery ledgers should include only accepted SWE. Failed, truly timed-out, and ambiguous candidates belong in process ledgers or `rejected_swe/`, not in `accepted_swe_*_latest`. Stale orchestration timeouts should remain auditable in `attempts.jsonl` while being requeued; they should not be counted as task runtime failures.

## Validated 2026 Multi-Language Production Lessons

The `multilang_swe_50` production run established the following observed pattern. Treat the numbers and repository mix as a case study, not as universal quotas:

- Production was expanded through canaries and bounded waves: 5 repaired candidates, then 15 total, then a 50-task delivery goal, followed by a C/C++ expansion. The final observed delivery contained 82 accepted bundles: 50 Go, 4 C, and 28 C++.
- The dominant blocker was raw trajectory patch/test quality, not the shared image. Do not rebuild the image repeatedly when both red and green reach the compiler/test runner. First classify patch applicability, test selection, verifier semantics, and dependency errors separately.
- C/C++ yield is repository-clustered. Reuse a proven repository adapter only inside the same repository/build contract, and still validate every instance. The observed C lane included htslib; C++ included CppUTest, PythonFMU, libuast, Luau, and yaml-cpp. These names are evidence of coverage, not permission to hardcode project-specific shortcuts globally.
- A small repository-specific repair can unlock multiple candidates, but it must remain narrow. The yaml-cpp focused static-library procedure is an example; it must not become a generic rule for all CMake projects.
- Repair waves must keep their bundles language-partitioned from the start. Reorganizing a flat `bundles/<id>` tree after validation risks stale manifests, incorrect relative paths, and bundles that only work in the producer workspace.
- The final handoff root is a product artifact, not a run directory. Move repair queues, logs, extracted worktrees, validation results, and backups to a sibling process-artifact directory before checksum and handoff.
- Store the shared image archive, its checksum, a loader, and a path-aware validator in the delivery. Critical-artifact checksums should cover the image, ledgers, scripts, and every bundle contract file. Vendored module trees may be large and hardlinked; document whether checksums cover every cache object and preserve hardlinks during transport when size matters.
- Direct-run portability is a separate gate from red/green. Copy or move at least one C, one C++, and one Go bundle to an unrelated path and run it from an unrelated current directory using only the bundle and shared image.

The September 2026 reference artifact was produced at `/data/huron/swe/work_20260907/multilang_swe_50` with shared image tag `swe-python-conda-runner:base-multilang-20260909`. Its shipped archive was `images/swe-python-conda-runner_base-multilang-20260909.tar.gz` with SHA256 `e98ac0ab04406b1c55b89ff792e71953a796054d07f8f8d588d6ef51e846c4de`. Known smoke representatives were `stepfun_185796` for C, `stepfun_1028510` for C++, and `stepfun_616312` for Go. These facts are useful for auditing that specific artifact only; always re-read its manifests and recompute checksums before acceptance instead of treating this paragraph as current proof.

### Language-neutral fake-verifier filter

Apply the static-oracle policy equally to Python, Go, C, and C++:

- Reject a test that reads implementation files and asserts strings, regexes, AST shapes, symbol placement, or exact snippets introduced by the gold patch.
- Reject a checker that reads `gold_patch.diff`, derives expected additions/removals, or decides success from a source marker.
- Compiling successfully is setup evidence, not automatically behavior evidence. A compile failure can count as the red behavior only when the task is specifically a compile-time defect, the same identity-bound command is used on both sides, and the gold side compiles and exercises the intended assertion.
- Configure, dependency, compile, link, loader, test-discovery, patch-application, and timeout failures are infrastructure/setup classes unless the issue itself and same-instance evidence prove otherwise.
- Shell wrappers must preserve the real test return code and emit exactly one parseable `OPENSWE_EXIT_CODE=<integer>` marker. Do not turn arbitrary log text into a pass/fail oracle.

### Promotion and delivery accounting

- Bundle presence is not acceptance. Promotion requires verifier-quality acceptance, independent patch preflight, strict delivery-local red/green, and one append-only accepted-ledger row.
- Compare the set of actual bundle IDs with every accepted ID/manifest/dataset ledger, not only line counts. Also verify that the recorded language equals the containing canonical directory.
- A changed bundle, patch, runner, dependency cache, image tag, or image archive invalidates downstream proof. Re-run the affected gate and refresh checksums; never carry forward an old green report by filename.
- Before handoff, run an independent read-only rollout audit. Read [openswe_multilang_rollout_validation.md](openswe_multilang_rollout_validation.md) for that contract.

## Skill Self-Evolution

After each substantial production batch, briefly reflect on pipeline failures and candidate pass rates. Before changing this skill, ask a subagent or reviewer to scrutinize the proposed lesson. Only promote lessons that are supported by user intent or observed validation evidence. Keep unproven build-system heuristics in run notes until they are validated across enough examples.

## Final Audits

Run audits before declaring a delivery complete:

```bash
ROOT=/path/to/verified_swe_output_by_language

wc -l \
  "$ROOT/ids.txt" \
  "$ROOT/manifest.jsonl" \
  "$ROOT/dataset.jsonl" \
  "$ROOT/accepted_swe_manifest_latest.jsonl" \
  "$ROOT/accepted_swe_ids_latest.txt" \
  "$ROOT/failed_swe_ids_latest.txt" \
  "$ROOT/failed_swe_manifest_latest.jsonl"

find "$ROOT"/bundles/c "$ROOT"/bundles/c++ "$ROOT"/bundles/golang \
  -mindepth 1 -maxdepth 1 -type d | wc -l

for lang in c 'c++' golang; do
  printf '%s ' "$lang"
  find "$ROOT/bundles/$lang" -mindepth 1 -maxdepth 1 -type d | wc -l
done

grep -RInE '/data/huron|/data/lwj|/Users/huron' \
  "$ROOT/README.md" "$ROOT/scripts" \
  "$ROOT/manifest.jsonl" "$ROOT/accepted_swe_manifest_latest.jsonl" \
  "$ROOT"/bundles/*/*/metadata.json 2>/dev/null || true

find "$ROOT" -maxdepth 3 \
  \( -name results -o -name runs -o -name validation_runs -o -name '*.log' \
     -o -name '*.bak' -o -name '*_tmp' -o -name '__pycache__' -o -name '._*' \) \
  -print | sort
```

The final report should include delivery root, image tag/tar, counts by language, validation kit commands, full red/green summary path, failed ids if any, path-independence audit result, and confirmation that validation outputs live outside the clean delivery root.
