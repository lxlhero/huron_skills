# Python Bundle-Local Mounted Delivery

This is the default Python production contract. It applies to both first-pass generation and static-oracle repair. Other-language adapters remain unchanged. A future explicit user request for image-only delivery may select the separate image builder; do not infer that request from “self-contained”.

## Runtime and ownership

- Use `swe-python-conda-runner:base-multilang-20260909` and record its immutable image identity. Do not bake each SWE environment into its own image in this mounted workflow.
- Every SWE directory owns its environment, source, Git objects/history required to reconstruct the declared base, gold/test patches, problem statement, fixture/data files, runtime declarations, and evidence. A synthetic seed commit plus a metadata base SHA is not exact repository identity proof.
- Copy or materialize the complete environment into the bundle. Shared conda and seed roots are build caches only. No final runner may search them, mount them, or silently fall back to an installed package outside the bundle-local runtime.
- Resolve host paths from the bundle entrypoint. Mount the selected bundle read-only at `/bundle`, its own environment at the fixed container prefix recorded in `runtime_manifest.json`, and an independent fresh writable run directory at `/work`. Record one concrete prefix per environment; preserve or repair embedded conda prefixes and validate executable/loader paths. A fixed container prefix is compatible with an arbitrarily relocated host bundle.
- Apart from the declared base image, only the shared validation kit is a shared executable dependency. Use a relative, version/hash-bound kit reference. Record its required location in the handoff; no dependency on producer staging directories or sibling SWE payloads is allowed.
- The base image archive is a local ordinary file inside each SWE directory. Identical archives may be hard-linked to save disk space. Copying one SWE independently must retain all bytes: no external symlinks, external archive pointers, or links back into cache roots. Environment/source files and auxiliary data follow the same ownership rule.

## Required per-SWE payload

Keep layout names aligned with the actual generator and runner; document them in the runtime manifest. The payload must contain:

- repository snapshot and required Git data, exact repo/base/tree proof (including export-subst-safe blob materialization)
- bundle-local environment and its dependency/version/hash identity; fixed container prefix
- local base archive, image tag and immutable image identity
- gold and dynamic test patches, executable evaluation and direct red/green entrypoints
- task/metadata, original problem statement, required fixtures/data and provenance
- relative-path file manifest, candidate seal, quality review and strict execution proof, final delivery seal

Do not promote an old shared-cache bundle by adding a manifest alone. Materialize the missing payload and rerun the gates. A lock file or dependency declaration is not a substitute for the delivered environment.

## Unified acceptance

1. Bind the original record, repository/base/tree identity, selected source patch and test evidence. Read the candidate's own issue and trajectory; do not generalize a neighboring test.
2. Semantically review every reconstructed Python verifier. It must exercise behavior, not gold/source markers, textual patch shape, or printed PASS. A filter pass alone does not replace semantic review. Preserve controls and distinguish setup/import/collection failures from the intended base behavior failure.
3. Preflight the exact patches independently and seal the self-contained candidate payload. Bind commands, environment, image and kit identities. Metadata assertions or a synthetic seed HEAD alone cannot establish an exact base tree.
4. Run strict base-red/gold-green in isolated fresh state, with present `OPENSWE_EXIT_CODE` markers, no timeout or infrastructure errors, and command execution proof. A changed payload invalidates downstream proofs.
5. Embed proofs and create a separate delivery seal. Copy or move the SWE to a new host path, make producer cache/seed/staging paths unavailable, and rerun direct red/green with networking disabled. Confirm imports, interpreter and loader resolve to the bundle-local payload. The archive must load the declared base on a destination without that image when testing image bootstrap.
6. Use the official workspace harvest entrypoint and its sealed eligibility checks; never directly edit accepted ledgers or copy a candidate into production to make it count. Perform direct post-harvest self-check; quarantine inactive/failed packages. Count only official active harvested outputs that passed these gates.

Keep generated candidates `accepted=false`, `harvest_eligible=false`, and `attempt_counted=false` until the corresponding gate actually authorizes a transition. Count real behavior attempts separately from infrastructure repair and unexecuted candidates.

## Current swe_prod project selection policy

This subsection records the current project scope, not a universal rule for all SWE datasets. Exclude `delivery_2000_repaired_good_verifier`'s old 2000 IDs and all known equivalent canonical-message and repo/base/issue groups. Rescan the full original JSONL for Python candidates rather than excluding the whole former 2302-ID pool. Deduplicate against currently selected problems as well; keep uncertain aliases for review and preserve original line/record hashes. Aim for 1600 newly repaired eligible SWE, but do not invent independent tasks, count duplicate aliases, weaken assertions or force the requested number when evidence/runtime gates fail. Report verified counts and the remaining gap.

## Tool compatibility

This contract does not imply that an older builder already implements it. Inspect generator, runner, relocation validator and official harvest capabilities before using their legacy command examples. If a helper still requires shared runtime caches or image baking, adapt and validate that helper in the authorized workspace or classify the candidate as packaging-blocked; do not weaken the ownership or acceptance contract.

## Bundled mounted-delivery tools

The skill ships `scripts/python_mounted/` with the converter, strict validator, source-origin helper, and validation launcher. These implement the current Python mounted contract; use them instead of an old shared-cache or image-baking helper for final packaging. Keep `verify_mounted.py` and `source_origin_helper.py` together in the shared kit: each candidate binds both file hashes. A kit change requires fresh packaging and validation.

The converter consumes an already sealed behavior candidate and its strict proof, a quiescent build environment, and the exact local base archive. It calls the workspace generator's `_selfpack_delivery_entries` interface, so verify compatibility with that generator before a batch. It never builds an image or changes the build cache. Its output remains pending, not an accepted delivery.

```bash
python3 "$SKILL_ROOT/scripts/python_mounted/mounted_bundle_conversion.py" \
  --bundle "$SOURCE_BUNDLE" --verification "$SOURCE_REDGREEN_JSON" \
  --expected-source-seal "$PROOF_BOUND_MANIFEST_SHA256" \
  --conda-root "$BUILD_CONDA_ROOT" --env-relative "envs/$ENV_NAME" \
  --base-image-archive "$LOCAL_BASE_ARCHIVE" \
  --generator "$WORKSPACE_GENERATOR" \
  --validator "$SKILL_ROOT/scripts/python_mounted/verify_mounted.py" \
  --output "$CANDIDATES/$INSTANCE_ID"

python3 "$SKILL_ROOT/scripts/python_mounted/canary.py" \
  --bundle "$RELOCATED_BUNDLE" \
  --validator "$SKILL_ROOT/scripts/python_mounted/verify_mounted.py" \
  --output "$RESULTS/$INSTANCE_ID.redgreen.json"
```

`RELOCATED_BUNDLE` must be an independent copy containing all environment and base-archive bytes, with producer caches unavailable. The launcher requires bundle-local mounts, no network and no script regeneration. Separately test archive bootstrap on a destination without the image. The shipped launcher does not create an empty Docker daemon or perform official harvest.

After semantic review, relocation and runtime gates pass, use the workspace's official harvester with this shared kit and the specified base image, then do a direct post-harvest self-check. Inspect harvester CLI compatibility instead of assuming an old CLI supports bundle-local environments. Do not manually append accepted ledgers.

The converter currently pins the project base image ID `sha256:ff79591fe576640163af45e25898e0e545f2ddd2f36e9933554cc347ca44faf8` and container conda root `/data/lwj/test/swe/python_conda_batch`. These are project configuration, not universal requirements for unrelated SWE work. The extra cold module-origin probe covers mypy only; other repositories still need their own import-origin assessment and behavior evidence.
