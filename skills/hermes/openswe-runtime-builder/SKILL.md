---
name: openswe-runtime-builder
description: Build, validate, repair, and package GAIR-NLP/OpenSWE-style mounted evaluation runtimes from raw sample.json or trajectory JSON. Use for first-pass SWE runtime production and mounted delivery across Python, Go, C, and C++; route image-only delivery, Python static-oracle repair, and ongoing production-stream operation to the associated child skills.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [swe, openswe, mounted-delivery, evaluation-runtime, multilang]
    related_skills: [openswe-python-oracle-repair, openswe-production-stream, swe-image-delivery, inference-platform-sandbox]
---

# OpenSWE Runtime Builder

This is the parent skill for turning raw SWE samples or trajectories into verified mounted OpenSWE runtime deliveries. Keep it focused on production, repair, validation, and packaging of mounted bundles. Use child skills for narrower downstream or operational workflows.

## Route First

- Existing verified mounted delivery to one Docker image per SWE, registry push, or image manifest: use `swe-image-delivery`.
- Large Python batch whose verifier may be source/gold/static oracle: use `openswe-python-oracle-repair`.
- Continuing the long-running lab production stream, wave batches, harvest queues, or remote progress ledgers: use `openswe-production-stream`.
- Heterogeneous platform sandbox validation of pushed SWE images: use `inference-platform-sandbox`.
- Mounted delivery creation, repair, validation, TOS/rclone upload, or raw sample/trajectory conversion: stay in this skill.

If a child workflow finds that the mounted bundle itself is wrong, return to this parent production/repair workflow before publishing or validating downstream artifacts.

## References

Read only the references needed for the current request:

- Python mounted delivery contract: [references/python-bundle-local-delivery.md](references/python-bundle-local-delivery.md).
- Generic pipeline stages and diagnosis: [references/pipeline_stages.md](references/pipeline_stages.md) and [references/openswe_pipeline.md](references/openswe_pipeline.md).
- Mounted delivery packaging, cleanup, and TOS/rclone upload: [references/openswe_mounted_delivery.md](references/openswe_mounted_delivery.md).
- Go/C/C++ or language-partitioned delivery: [references/openswe_multilang_delivery.md](references/openswe_multilang_delivery.md).
- Independent rollout/acceptance verification: [references/openswe_multilang_rollout_validation.md](references/openswe_multilang_rollout_validation.md).
- First-pass production hardening: [references/first-pass-swe-production.md](references/first-pass-swe-production.md).
- Python static-oracle repair details, when not using the child skill directly: [references/python-static-oracle-production.md](references/python-static-oracle-production.md).

Implementation reference for the full production script package (local, not vendored into this skill): `/Users/huron/code/ai_lab/swe_reference_scripts_20260916` with its `SCRIPT_INVENTORY.txt` index.

Use shipped helper scripts when they fit instead of retyping large workflows:

```text
scripts/run_pipeline.py
scripts/python_mounted/
```

## Core Contract

Default output is a mounted delivery: one shared base image plus per-SWE bundles and fresh writable run directories. Each accepted SWE bundle must be independently ownable and runnable from an unrelated host path.

Every accepted bundle must include the files needed for its language and runner, normally:

```text
task.json
metadata.json
gold_patch.diff
test_patch.diff
run_mounted_eval.sh
problem statement files
source snapshot/archive or exact source materialization data
language-specific dependency payloads such as Python envs or Go module cache
```

Canonical multi-language bundle roots are:

```text
bundles/python/<id>
bundles/golang/<id>
bundles/c/<id>
bundles/c++/<id>
```

Use `golang`, `c`, and `c++` as canonical labels. Do not create both `cpp` and `c++`; normalize public manifests and delivery paths to `c++` unless the user explicitly asks otherwise.

## Acceptance Gates

Acceptance is strict and layered:

1. Evidence must bind the issue, repository, base commit, patches, test commands, runtime image/toolchain, and verifier to the same SWE instance.
2. `test_patch` and `gold_patch` must preflight independently against clean worktrees. Do not continue as if a failed patch applied.
3. Verifier quality must be dynamic: reject tests whose primary assertion is exact gold-source shape, source marker text, or static file snippets rather than externally observable behavior.
4. Mounted red/green must emit parseable markers: `testonly` requires present nonzero `OPENSWE_EXIT_CODE`; `gold` requires `OPENSWE_EXIT_CODE=0`.
5. Missing markers, timeouts, swallowed patch errors, or process exit status without `OPENSWE_EXIT_CODE` are failures.
6. Delivery handoff must pass static marker scan, external path scan, conda/path scan when applicable, ledger/bundle set equality, patch preflight, delivery-local red/green, and path/relocation checks.

High-recall static-oracle signals include:

```text
gold_patch_static_discriminator
source_marker_oracle
static source-content oracle
dependency-light source-content oracle
oracle_static_
oracle_source_check_
ORACLE_STATIC_FAIL
openswe_oracle_test.py
expected_added
missing marker
```

A keyword hit can require semantic review, but an explicit source/gold oracle is a hard rejection even if runtime red/green passes.

## Language Notes

- Python: read `python-bundle-local-delivery.md`. The current mounted contract is bundle-local environment/source/data plus a declared base image and validation kit. Shared conda/seed roots are build caches only, not final runtime dependencies.
- Go: preserve offline module state such as `bundle/deps/go-mod`; a `--network none` red/green pass is strong evidence that no module fetch remains. Some trajectory repros are standalone `package main` programs and must be run with `go run` in addition to normal `go test` when encoded by the bundle.
- C: preserve source snapshots, patches, compiler commands, and focused test adapters. Build products should go under `/work`, not the clean bundle.
- C++: require the needed `g++`, `cmake`, `make` or `ninja` toolchain and keep project-specific focused repro adapters. Do not generalize repository-specific repairs.

## Workflow

1. Inspect the user request and choose the route. If this is image-only delivery from an existing mounted delivery, stop here and use `swe-image-delivery`.
2. Read the relevant reference files before generating, repairing, validating, packaging, or uploading.
3. Inspect the current workspace scripts rather than assuming stale flags. For the generic portable pipeline, start with `scripts/run_pipeline.py`; for Python mounted packaging, prefer `scripts/python_mounted/`.
4. Materialize candidates with explicit evidence and language labels.
5. Build or load the declared base image without weakening the Python runner when adding Go/C/C++ toolchains.
6. Generate bundles in a staging area first. Do not mutate durable accepted output until the verification/harvest gate admits the SWE.
7. Run verifier-quality checks and strict mounted red/green before adding anything to accepted ledgers.
8. Package only clean accepted artifacts. Process logs, temporary run roots, and validation outputs should live outside the clean delivery root by default.
9. Report exact counts, paths, failed/rejected reasons, and the commands needed to re-run validation.

## Safety

- Do not start batch workers, remote production workers, registry pushes, or destructive cleanup unless the user explicitly authorizes that action.
- Do not write `GITHUB_TOKEN`, SSH passwords, gateway secrets, AK/SK, or other credentials into skill files, project files, shell profiles, helper scripts, or logs.
- Do not run global `docker image/container/system prune`.
- Do not delete, rewrite, prune, rebuild, overwrite, or silently reuse already accepted production bundles, verified id files, manifest rows, latest accepted ids, or delivery ledgers.
- Do not close production DB tasks with raw SQL or run risky DB mode changes such as `PRAGMA journal_mode=DELETE` on production databases.
- Protect concurrent workers with locks for attempt state, repo+commit source materialization, and production append/ledger mutation.
- Append accepted SWE only through the official validation/harvest gate; never manually copy staging bundle directories into production or edit ledgers to fake acceptance.

Read-only inspection of workspaces, ledgers, and logs may proceed without extra authorization. Starting workers, pushing anything, deleting sandboxes, or mutating production ledgers requires explicit user authorization first.

## Diagnosis

For stage-level troubleshooting, read `references/pipeline_stages.md`. Common decisions:

| Symptom | Action |
| --- | --- |
| Low eval-ready count | Inspect `pipeline_summary.json`, candidate filters, and missing patch/source reasons. |
| Missing source | Re-materialize exact repo/base commit with source locks; do not use a nearby commit. |
| Missing test patch | Recover from GitHub PR or same-instance trajectory evidence; do not fabricate. |
| Mounted verify passes but verifier checks source markers | Quarantine as static oracle and repair behavior verifier before harvest or delivery. |
| Conda/env import failure | Repair build-cache under lock, then materialize the bundle-local final env and revalidate. |
| Go missing modules under no-network validation | Repair/copy module cache into the bundle before acceptance. |
| C/C++ missing tools | Fix base/toolchain or bundle dependency capture, then rerun red/green. |
| Red exits 0 | Reject or repair test selection; accepted `testonly` must be nonzero. |
| Gold exits nonzero or lacks marker | Reject or repair patch, command, runtime, or dependency setup. |
| Validation writes into clean delivery | Fix defaults so results/runs/logs go to a sibling process directory. |

## Reporting

Always state which stages actually ran. Include the relevant subset of:

- input sample/trajectory paths and selected ids
- language distribution and canonical bundle roots
- base image tag/archive and validation kit identity
- red/green report path and `OPENSWE_EXIT_CODE` interpretation
- verifier-quality/static-oracle audit result
- accepted/rejected/failed counts and dominant failure classes
- delivery root, package path, upload destination, or registry/image handoff route
- explicit note that production/delivery ledgers were or were not mutated

## Notes

This skill does not ship `openswe_gair_runtime`; point `--workspace` to a checkout that contains it. Keep private hostnames, paths, and credentials as runtime configuration or project context, not universal skill defaults.
