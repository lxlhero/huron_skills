# OpenSWE Pipeline Reference

For Python mounted production, apply [python-bundle-local-delivery.md](python-bundle-local-delivery.md). Shared conda/seed paths in build examples are staging caches, never final runtime dependencies. Each SWE owns its environment, source/Git, data and local base archive; only the base runtime and version-bound validation kit are shared. Explicit image-only requests and other-language adapters remain separate.


## Goal

Given a raw `sample.json` or trajectory JSON, automatically produce a portable OpenSWE evaluation runtime that can be copied to another machine and used for user/model patch evaluation. The default Python delivery shape is mounted bundles, each containing its own environment, source/Git and local base archive; after mounted red/green verification, a user may also request one self-contained Docker image per SWE.

Implementation roots:

```text
/Users/louwenjie/Downloads/lwj/swe/openswe_gair_runtime
/data/lwj/test/swe/openswe_gair_runtime
```

## End-to-End Stage Map

1. `build_openswe_from_raw_sample.py`
   - Parse raw trajectory JSON.
   - Extract `instance_id`, `repo`, `base_commit`, `problem_statement`, language, and final trajectory/replay diff.
   - Split diff into candidate `patch` and candidate `test_patch` by test-file paths.
   - Output repo/base candidates and a report.

2. Python environment enrichment in `build_portable_openswe_pipeline.py`
   - Keep Python tasks.
   - Infer Python version.
   - Attach `python_env_name`, `python_env_path`, `has_local_source`, and local source path.
   - Reject or repair missing source/env before validation.

3. `recover_github_pr_test_patch.py`
   - Search GitHub PRs using repo, issue title, base commit, and patch evidence.
   - Score candidates by base/parent alignment, title similarity, path overlap, code similarity, and test patch applicability.
   - Split recovered PR diff into `gold_patch` and `test_patch`.
   - With `--use-pr-code-patch`, replace trajectory patch with recovered PR code patch.
   - Use `--workers N` for task-level parallel recovery.

4. `03_eval_ready.jsonl`
   - Keep only rows with repo/base_commit, Python language, source, gold patch, and test patch.
   - Include `patch_source` and `test_patch_source`.
   - Inferred test patches remain provisional until mounted red/green passes.

5. `generate_conda_eval_artifacts.py`
   - Generate repo snapshot, Dockerfile, eval scripts, and task.json under `output/<task_id>/`.
   - Infer pytest command from `test_patch`.
   - Use `python_conda_batch/envs/<task_id>_pyXX` only as a build cache; materialize the environment into the candidate bundle before final validation.

6. `evaluate_user_patch.py prepare-bundles`
   - Create task bundles under `eval_reconstruction/bundles/<task_id>/`.
   - Required bundle files:
     - `repo/`
     - `task.json`
     - `gold_patch.diff`
     - `test_patch.diff`
     - `eval_skeleton.sh`
     - `eval_testonly.sh`
     - `eval_gold.sh`
     - `run_mounted_eval.sh`
     - `metadata.json`

7. `evaluate_user_patch.py mounted-verify`
   - Use `swe-python-conda-runner:base-multilang-20260909`.
   - Mount bundle read-only.
   - Mount only the bundle-local Python environment at its recorded fixed container prefix.
   - Mount writable `runs`.
   - Required red/green result:
     - `testonly` fails.
     - `gold` passes.
   - A task is verified only when `metadata.json` records `mounted_status == "verified"`.

8. `export_eval_manifest.py`
   - Write verified manifest and summary.
   - Use these counts in the final answer.

9. Optional self-contained per-SWE image build
   - Run this only from already mounted red/green verified bundles.
   - For current image delivery from an existing mounted delivery, use the associated `swe-image-delivery` skill and its multi-language builder.
   - `scripts/build_selfcontained_images.py` is a legacy Python/conda helper; do not use it for Go/C/C++ or registry-scale delivery.
   - Base image is `swe-python-conda-runner:base`.
   - Image repository is always `swe-python-conda-runner`; use tags such as `swe-python-conda-runner:<task_id>`.
   - The image must include `/bundle`, `/problem`, labels, and `describe`, `testonly`, and `gold` entrypoint modes.

10. `package_portable_openswe_runtime.py`
   - Create a relocatable package containing:
     - one base image tar
     - verified bundles
     - conda envs and caches
     - service/client code
     - install/start/smoke scripts
     - `deploy_manifest.json`
   - If self-contained images were requested, report image tags and verification logs alongside the portable package; do not replace the verified bundle manifest.

## Full Remote Execution

For the known remote host and dataset, run:

```bash
python3 /data/lwj/test/swe/openswe_gair_runtime/scripts/build_portable_openswe_pipeline.py \
  --sample-json /data/lwj/test/swe/sample.json \
  --run-dir /data/lwj/test/swe/new \
  --min-confidence high \
  --github-workers 8 \
  --materialize-missing-source \
  --source-workers 8 \
  --pip-index-url https://pypi.tuna.tsinghua.edu.cn/simple \
  --pip-trusted-host pypi.tuna.tsinghua.edu.cn \
  --run-build \
  --run-mounted-verify \
  --package
```

Use `--package-dry-run` only when explicitly testing packaging inputs without copying large files.

## Parallelism Rules

- Use `--github-workers 8` for full recovery by default.
- Use `--materialize-missing-source --source-workers 8` for the known raw dataset so missing repo/base sources are cloned and checked out before patch recovery.
- Use Tsinghua mirrors for Python package installation by default: pip through `--pip-index-url https://pypi.tuna.tsinghua.edu.cn/simple` and conda through `python_conda_batch/.condarc`.
- Increase workers only if GitHub rate limits and remote CPU/I/O allow.
- For build/verify, parallelize only if the pipeline has non-colliding output directories or explicit worker support.
- If manually sharding task IDs, write each shard to a separate run dir and merge manifests after all shards finish.

## Repair Rules

If `03_eval_ready.jsonl` is unexpectedly small:

1. Inspect `pipeline_summary.json`.
2. If rejected due to `missing_local_source`, materialize seed repos/worktrees for those repo/base pairs, then rerun.
3. If rejected due to `missing_test_patch`, inspect GitHub recovery report. Try lower confidence only if the user accepts weaker evidence, and still require red/green.
4. If rejected due to `missing_gold_patch`, use recovered PR code patch when high confidence is available. Otherwise keep it rejected.
5. If conda env is missing, create it under `python_conda_batch/envs` and preserve package caches for deployment.

## Deployment Verification

After packaging, on the same machine or a target machine:

```bash
cd <portable-package>
bash install/load_image.sh
bash install/start_service.sh
bash install/smoke_test.sh
```

The smoke test must call the FastAPI service and run at least one mounted evaluation.

## Reporting Template

Report:

```text
input_count
repo_base_count
python_candidate_count
eval_ready_count
mounted_verified_count
failed/rejected counts by reason
portable_package_path
base_image_tar
conda_root
bundle_root
deploy_manifest
smoke_test result
self_contained_images (if requested)
```

Do not say "all tasks passed" unless mounted red/green verification actually passed for all tasks in the final verified manifest.
