# OpenSWE Pipeline Stages Reference

For Python mounted production, apply [python-bundle-local-delivery.md](python-bundle-local-delivery.md). Shared conda/seed paths in build examples are staging caches, never final runtime dependencies. Each SWE owns its environment, source/Git, data and local base archive; only the base runtime and version-bound validation kit are shared. Explicit image-only requests and other-language adapters remain separate.


## Stage Map

### Stage 0 — Input Materialization
Script: built into `build_portable_openswe_pipeline.py`  
Output: `<run-dir>/00_input_sample_subset.json`

Loads `sample.json`, applies `--ids` / `--limit` filter, writes subset.

---

### Stage 1 — Repo/Base Candidate Selection
Script: `build_openswe_from_raw_sample.py`  
Output: `01_repo_base_candidates.jsonl`, `01_repo_base_candidates_report.jsonl`

Parses trajectory JSON. Extracts:
- `instance_id`, `repo`, `base_commit`, `problem_statement`
- Final trajectory/replay diff → splits into candidate `patch` + `test_patch` by test file paths
- Language detection

Rejects rows missing `repo` or `base_commit`.

---

### Stage 1b — Python Environment Enrichment
Output: `01_python_env_candidates.jsonl`

Filters to Python-only tasks. Infers Python version. Attaches:
- `python_env_name`, `python_env_path`
- `has_local_source`, local source path

Rejects tasks where Python version cannot be inferred.

---

### Stage 1c — Source Materialization (optional)
Triggered by: `--materialize-missing-source`  
Workers: `--source-workers` (default 8)

For each task missing local source:
1. Try GitHub commit archive download
2. Fall back to precise `git fetch <commit>`
3. Fall back to `git clone --mirror` (only with `--allow-full-git-mirror-fallback`)

Output: `01b_repo_base_candidates_after_source.jsonl`

---

### Stage 2 — GitHub PR Patch Recovery
Script: `recover_github_pr_test_patch.py`  
Output: `02_recovered_patches.jsonl`, `02_recovered_patches_report.jsonl`  
Workers: `--github-workers`  
Confidence: `--min-confidence` (low/medium/high)

Searches GitHub PRs using: repo, issue title, base commit, patch evidence.  
Scores candidates by: base/parent alignment, title similarity, path overlap, code similarity, test patch applicability.  
Splits recovered PR diff into `gold_patch` and `test_patch`.  
Records evidence chain for every recovered test patch.

Skip with `--skip-github-recovery` (keeps trajectory-derived patches only).

---

### Stage 3 — Eval-Ready Selection
Output: `03_eval_ready.jsonl`

Keeps only rows with ALL of:
- `repo` + `base_commit` present
- `language == python`
- Local source available
- `gold_patch` present
- `test_patch` present

Records `patch_source` and `test_patch_source` on each row.

**This is the key diagnostic output.** If count is lower than expected, check `pipeline_summary.json → rejected_reasons`.

---

### Stage 4 — Artifact Generation
Script: `generate_conda_eval_artifacts.py`  
Output: `<output-root>/<task_id>/`

Per task:
- Repo snapshot
- Dockerfile
- Eval scripts (`eval_skeleton.sh`, `eval_testonly.sh`, `eval_gold.sh`)
- `task.json`
- Infers pytest command from `test_patch`
- Creates build-cache conda env (materialize into each Python bundle before acceptance): `<conda-root>/envs/<task_id>_pyXX`

---

### Stage 5 — Bundle Preparation
Script: `evaluate_user_patch.py prepare-bundles`  
Output: `<bundle-root>/<task_id>/`

Required files per bundle:
```
repo/
task.json
gold_patch.diff
test_patch.diff
eval_skeleton.sh
eval_testonly.sh
eval_gold.sh
run_mounted_eval.sh
metadata.json
```

---

### Stage 6 — Mounted Red/Green Verification
Script: `evaluate_user_patch.py mounted-verify`  
Docker image: `swe-python-conda-runner:base-multilang-20260909`

Mounts:
- Bundle directory (read-only)
- Bundle-local Python environment at the fixed prefix recorded in `runtime_manifest.json` (read-only; no shared conda-root mount)
- `<bundle-root>/<task_id>/runs/` (writable)

Required result for a task to be **verified**:
- `testonly` run: **FAILS** (tests fail without gold patch — confirms tests are discriminating)
- `gold` run: **PASSES** (tests pass with gold patch applied)

`metadata.json` must record `mounted_status == "verified"`.

---

### Optional Stage 6b — Self-Contained Per-SWE Docker Images
Current workflow: use the associated `swe-image-delivery` skill and its multi-language builder for image delivery from an existing mounted delivery.  
Legacy helper: `scripts/build_selfcontained_images.py` is Python/conda-oriented and should not be used for Go/C/C++ or registry-scale delivery.  
Base image: `swe-python-conda-runner:base`  
Image repository: `swe-python-conda-runner`

Run only after mounted red/green verification has accepted the task. Each task image uses a task-specific tag, for example:

```text
swe-python-conda-runner:stepfun_1668634
```

Required image behavior:
- `describe` prints repo, base commit, environment, problem statement, and test commands.
- `testonly` runs red tests without dependency/path mounts and must emit nonzero `OPENSWE_EXIT_CODE`.
- `gold` runs green tests without dependency/path mounts and must emit `OPENSWE_EXIT_CODE=0`.
- Mounting `/input/test_patch.diff` replaces the built-in test patch for user-generated test validation.

Required image metadata:
- `/bundle/task.json`
- `/bundle/metadata.json`
- `/problem/README.md`
- `/problem/statement.txt`
- Docker labels including `openswe.task.id`, `openswe.repo`, `openswe.base_commit`, and `openswe.problem.statement`

---

### Stage 7 — Manifest Export
Script: `export_eval_manifest.py`  
Output: `eval_manifest.jsonl`, `eval_summary.json`

Writes verified manifest. Use `mounted_verified_count` from this, not from stage 3.

---

### Stage 8 — Portable Packaging
Script: `package_portable_openswe_runtime.py`  
Triggered by: `--package`

Creates relocatable package:
```
openswe_runtime_package_<timestamp>/
  bundles/<task_id>/env/
  bundles/<task_id>/base_image.tar
  openswe_gair_runtime/
    eval_reconstruction/bundles/<task_id>/
    eval_reconstruction/reports/
    scripts/
    service/
    data/
    debug_inputs/
  install/
    load_image.sh
    start_service.sh
    stop_service.sh
    smoke_test.sh
  deploy_manifest.json
  DEPLOYMENT.md
```

Package only runs if all prerequisites exist (verified bundles, conda envs, base image tar).

---

## Rejection Reason Reference

| Reason | Meaning | Fix |
|--------|---------|-----|
| `missing_repo_or_base_commit` | Stage 1 parse failed | Check raw trajectory format |
| `not_python` | Non-Python task | Expected; not a bug |
| `unparseable_python_version` | Could not infer Python version | Add to `data/python_version_overrides.json` |
| `missing_local_source` | Repo/commit not materialized | Run `--materialize-missing-source` |
| `missing_test_patch` | No test patch from trajectory or GitHub | Check GitHub recovery report; consider lower confidence |
| `missing_gold_patch` | No gold patch | Use recovered PR code patch if high-confidence; otherwise drop |
| `inferred_test_not_verified` | Inferred test patch failed red/green | Inspect Docker logs; may need manual test patch |
| `nondiscriminating_test` | testonly run passed (test doesn't fail without patch) | Drop or repair test_patch |

---

## Intermediate File Locations

```
<run-dir>/
  00_input_sample_subset.json
  01_repo_base_candidates.jsonl
  01_repo_base_candidates_report.jsonl
  01_python_env_candidates.jsonl
  01b_*                           (after source materialization, if run)
  02_recovered_patches.jsonl
  02_recovered_patches_report.jsonl
  03_eval_ready.jsonl
  pipeline_summary.json
  retry_attempts.jsonl
  logs/

<workspace>/
  output/<task_id>/               (generated artifacts)
  eval_reconstruction/bundles/<task_id>/   (bundles)
  eval_reconstruction/reports/    (verify reports)
  data/github_pr_cache/           (cached GitHub API responses)
```
