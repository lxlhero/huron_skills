---
name: swe-image-delivery
description: Build, locally validate, push, and manifest self-contained Docker images from an existing OpenSWE mounted delivery, including Python, Go, C, and C++ bundle differences. Use after openswe-runtime-builder has already produced a verified mounted delivery.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [swe, openswe, docker, image-delivery, registry, multilang]
    related_skills: [openswe-runtime-builder, inference-platform-sandbox]
---

# SWE Image Delivery

Use this skill when the user has an existing OpenSWE mounted delivery and wants one Docker image per SWE instead of runtime host mounts. This is an associated follow-on skill for `openswe-runtime-builder`: use `openswe-runtime-builder` to produce or repair the mounted delivery, then use this skill to turn verified bundles into image tags, run small-batch/no-mount validation, push the accepted images, and write a delivery manifest.

## Scope

Start from a clean mounted delivery root, usually shaped like:

```text
delivery/
  accepted_swe_ids_latest.txt
  accepted_swe_manifest_latest.jsonl
  manifest.jsonl
  bundles/
    python/<id>/
    golang/<id>/
    c/<id>/
    c++/<id>/
```

Do not use this skill to infer patches, repair tests, harvest candidates, or decide whether a SWE belongs in the delivery. Those are parent-skill responsibilities. This skill assumes every selected bundle has already passed strict mounted red/green and verifier-quality gates.

## Required Contract

- Build from the requested base image, normally `swe-python-conda-runner:base` or a fully qualified registry tag ending in `:base`.
- Use repository name `swe-python-conda-runner`; use the SWE id as the image tag, for example `swe-python-conda-runner:stepfun_1003645`.
- Embed the selected bundle at `/bundle`, problem text at `/problem`, and an entrypoint that supports `describe`, `testonly`, and `gold`.
- Validate images without the original bundle mount. For `testonly`, require a present nonzero `OPENSWE_EXIT_CODE`; for `gold`, require `OPENSWE_EXIT_CODE=0`.
- Push only images that pass local no-mount validation, unless the user explicitly asks for build-only output.
- Do not modify mounted delivery contents, persist credentials, run global Docker prune, or delete unrelated Docker images.

## Workflow

1. Read [references/multilang-image-delivery.md](references/multilang-image-delivery.md) before building, validating, or pushing images from a multi-language delivery.
2. Confirm bundle count and ledger count match. Resolve ids from `accepted_swe_ids_latest.txt` unless the user provides a subset.
3. Run a small batch first when the registry, base image, script, or platform is new. Include at least one representative language when possible.
4. For the small batch, run local no-mount validation. If requested, additionally validate those images through the heterogeneous Sandbox platform using `inference-platform-sandbox`.
5. For the remaining/full batch, local no-mount validation is enough unless the user asks for Sandbox validation again.
6. Write a manifest under the user-requested path. Include id, language, repository, base commit, image tag, digest when available, validation status, push status, and log paths.

## Helper Script

Use `scripts/build_multilang_selfcontained_images.py` when available rather than rewriting the image-builder. It supports nested `bundles/<language>/<id>` deliveries and copies the full bundle into the image, so Go module caches and C/C++ test harness files travel with the tag.

Standard shape:

```bash
python3 scripts/build_multilang_selfcontained_images.py \
  --delivery-root /path/to/delivery \
  --ids-file /path/to/ids.txt \
  --output-root /path/to/image_build_runs/run_YYYYMMDD_HHMMSS \
  --base-image registry.example/team/swe-python-conda-runner:base \
  --image-repository registry.example/team/swe-python-conda-runner \
  --verify \
  --push \
  --timeout-seconds 2400
```

Use `--sudo-docker` only on hosts where Docker auth is stored under root and the command must run as root.

## Authorization

Read-only inspection of the delivery root, bundle counts, and local image inspection may proceed without extra authorization. Building images is local and low-risk, but registry push requires explicit user authorization first, since it publishes artifacts outside this machine.

## Reporting

Report the run directory, counts built/validated/pushed, failures with log paths, and manifest path. If any image fails validation or push, stop describing it as delivered; give the exact id, language, failing mode, `OPENSWE_EXIT_CODE` if present, and the log to inspect.

For normal deliveries, the manifest can be grouped by language listing SWE id and image tag. Include digest, inspect output, and build/push logs only for debug, audit, or incident review.
