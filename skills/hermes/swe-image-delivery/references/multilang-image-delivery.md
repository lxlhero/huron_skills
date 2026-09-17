# Multi-Language SWE Image Delivery

Use this reference for image-only delivery from an existing OpenSWE mounted delivery. The parent mounted delivery remains the source of truth; image delivery is a packaging and validation step.

## Preconditions

- The delivery root has canonical nested bundles: `bundles/python`, `bundles/golang`, `bundles/c`, and/or `bundles/c++`.
- `accepted_swe_ids_latest.txt` and the accepted manifest agree with the bundle tree.
- Every selected SWE has already passed mounted strict red/green and verifier-quality review.
- The base image is available locally or pullable from the target registry.
- Docker auth is already configured in the environment that runs Docker. Do not write passwords or tokens into helper scripts, shell profiles, or logs.

## Image Contents

Each image must contain exactly one selected SWE bundle:

```text
/bundle/
  task.json
  metadata.json
  gold_patch.diff
  test_patch.diff
  run_mounted_eval.sh
  source archive/snapshot
  problem files
  deps/                  # optional, language-specific caches
/problem/
  README.md
  statement.txt
/usr/local/bin/openswe-selfcontained
/work/                   # writable runtime root
```

The entrypoint should accept:

```bash
docker run --rm IMAGE describe
docker run --rm --network none IMAGE testonly
docker run --rm --network none IMAGE gold
```

`describe` must print useful task context. `testonly` and `gold` must invoke `/bundle/run_mounted_eval.sh` from an unrelated working directory with `OPENSWE_WORK_ROOT=/work`.

## Validation Contract

Validation is based on the `OPENSWE_EXIT_CODE` marker, not the container process exit status alone.

```text
testonly: OPENSWE_EXIT_CODE present and nonzero
gold:     OPENSWE_EXIT_CODE present and 0
missing marker: failure
timeout:        failure
```

Run `testonly` and `gold` with `--network none` to prove the image does not depend on external package fetches or host mounts.

## Language Differences

### Python

Python bundles may require a task conda or virtualenv path expected by the runner. When a mounted delivery keeps the environment inside the bundle, copy it unchanged. When the environment is shared outside the bundle, the image builder must copy it into the same absolute or runner-expected path and update only image-local paths. Do not point the image at producer cache directories.

Python verifier reliability is especially prone to static source oracles. Before image delivery, confirm the parent delivery already rejected tests that read source files or gold patches to assert exact snippets.

### Go

Go images must carry offline module state. Preserve `bundle/deps/go-mod` when present and let `run_mounted_eval.sh` map it into the work root or Go environment. A `--network none` pass is the proof that no module download is still required.

Be careful with standalone Go repros. Some accepted bundles intentionally run a `package main` / `func main` repro with `go run`; true `_test.go` files with `TestXxx`, `FuzzXxx`, or `BenchmarkXxx` use `go test`. Do not rewrite the bundle logic while image-packaging it.

### C

C images rely on source snapshots, patches, compiler toolchains, and focused test commands already encoded in the bundle. The image should preserve generated test files and build scripts, but build products must be created under `/work`, not inside `/bundle`.

The base image must provide `gcc`, `make`, `cmake` or project-specific build tools required by the bundle. A gold failure with compiler or missing-library output is an image/base dependency problem unless the mounted delivery had the same failure.

### C++

C++ images have the same `/work` build-output requirement as C and normally need `g++`, `cmake`, `make` or `ninja`, and project libraries captured by the bundle. Keep canonical language name `c++` in manifests and paths; do not convert it to `cpp` except inside Docker tag-safe metadata if a tool cannot handle `+`.

Some C++ bundles use focused repro binaries instead of upstream full test suites. Preserve the bundle's adapter exactly; image delivery should not generalize repository-specific repairs.

## Small Batch Then Full Push

For a new registry/base/script combination:

1. Select a small representative id set, ideally covering Go, C, and C++ if available.
2. Build images from the target base and repository.
3. Run `describe`, `testonly`, and `gold` locally without mounts.
4. Push only passing tags.
5. If requested, launch heterogeneous Sandbox validation for the small batch and delete temporary sandboxes afterward.

After the user accepts the small batch, run the remaining or full id set through the same local validation and push flow. Do not rerun Sandbox validation unless the user asks.

## Manifest Fields

Write JSON and, when useful, TSV/Markdown summaries with:

- `id`
- `language`
- `repo`
- `base_commit`
- `image`
- `digest`
- `bundle`
- `build_log`
- `describe_status`
- `testonly_status`
- `testonly_openswe_exit`
- `gold_status`
- `gold_openswe_exit`
- `push_status`
- `sandbox_status` for any small-batch Sandbox validation

Derive language from the bundle path, not from the SWE id. Prefer `docker manifest inspect` or registry data for final remote digests when available.

## Failure Handling

If a build fails, inspect the per-id build log before retrying. If validation fails, inspect the mode log and compare with the mounted delivery behavior. Retry only after identifying a real packaging, base-image, or transient infrastructure cause.

Do not patch `gold_patch.diff`, `test_patch.diff`, `run_mounted_eval.sh`, source snapshots, or manifests in the delivered bundle during image delivery. If the bundle itself is wrong, hand it back to the parent `openswe-runtime-builder` repair workflow.
