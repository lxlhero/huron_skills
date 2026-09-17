# Shift-Left First-Pass SWE Production

For Python mounted production, apply [python-bundle-local-delivery.md](python-bundle-local-delivery.md). Shared conda/seed paths in build examples are staging caches, never final runtime dependencies. Each SWE owns its environment, source/Git, data and local base archive; only the base runtime and version-bound validation kit are shared. Explicit image-only requests and other-language adapters remain separate.


Use this reference when producing new OpenSWE runtimes for the first time. Its purpose is to prevent defects that would otherwise become a later repair batch. Use a shared strict production kernel for all languages and a language adapter only for dependency, build, and test semantics.

## Principle

Do not first emit a weak bundle and plan to repair it later. Make the first production pass prove the same invariants required after repair:

- original task/trajectory evidence is bound to the instance
- the repository is the exact declared base revision
- the verifier is dynamic and issue-specific
- dependencies and toolchain are complete enough to execute the intended test
- patches apply on independent clean snapshots
- testonly is behavior-red and gold is green
- the bundle is self-contained apart from the declared base image and validation kit; Python dependency environments and source/Git are bundle-local
- proof is sealed and harvest is transactional
- post-harvest direct validation succeeds before the bundle becomes active output

Static-oracle detection is a generation gate, not a downstream cleanup filter.

## First-Pass State Machine

Use explicit, persisted states:

1. `evidence_bound`
2. `repo_identity_materialized`
3. `dynamic_verifier_synthesized`
4. `dependency_and_toolchain_preflight_passed`
5. `selfpack_candidate_sealed`
6. `quality_gate_passed`
7. `patch_preflight_passed`
8. `strict_redgreen_passed`
9. `delivery_proof_sealed`
10. `harvest_transaction_committed`
11. `post_harvest_selfcheck_passed`
12. `active_production_bundle`

Every transition must bind to the same instance ID, base revision, patch hashes, verifier command hash, environment/toolchain identity, and bundle seal. A changed payload invalidates downstream proof.

Route failures by stage. Do not collapse them into a generic failed list:

- evidence or semantic repair queue
- repository/seed infrastructure queue
- dependency/toolchain repair queue
- patch-context repair queue
- verifier behavior repair queue
- infrastructure retry queue
- quarantine/recovery queue

## What to Shift Left for Python

Apply these checks before a Python bundle becomes a validation candidate:

- Normalize the exact executable command across `python`, `python -m pytest`, and `pytest` forms without changing semantics.
- Reconstruct tests only from files created or edited in the same trajectory and subsequently executed.
- Use unified-diff plus Python AST inspection to require a real runtime assertion or explicit behavior exit.
- Reject print-only PASS/FAIL scripts unless their computed condition is converted to an assertion or exit status.
- Reject source reads, gold markers, expected-add/remove strings, and stdout-text oracles.
- Prove the same normalized command has base nonzero and gold zero evidence when trajectory evidence is used for automatic admission.
- Build a dependency declaration from `pyproject.toml`, `setup.py`, `setup.cfg`, requirement files, task metadata, and observed imports.
- Before behavior validation, run import/collection preflight and distinguish missing packages, ABI conflicts, Python-version mismatch, solver failure, and test-path failure.
- Bind the conda environment name, Python version, dependency lock/declaration hashes, and cache identity in `runtime_manifest.json`.
- Treat host paths and container prefixes as different namespaces. Final Python runtime resolution uses only the bundle-local environment mounted at the fixed prefix in the runtime manifest, without external cache fallback.
- Serialize shared conda build-cache mutation; copy/materialize the resolved environment into each bundle and mount that bundle-local environment read-only for final validation.
- Classify missing `numpy`, `toolz`, pytest plugins, or other imports as environment repair, never behavior-red.

Python-specific logic belongs in the Python adapter. Repository identity, patch preflight, proof sealing, harvest, transactions, and attempt accounting stay in the shared kernel.

## Cross-Language Strict Production Kernel

The following rules apply unchanged to Python, Go, C, C++, and future languages:

- Use full repository revision identity and verify tree/content, not a directory name or sentinel alone.
- Materialize from an exact seed object; missing seed objects are infrastructure requeues.
- Build a dynamic behavior verifier from same-instance evidence.
- Deny source/gold-marker oracles and unknown verifier quality.
- Apply test and gold patches on separate clean snapshots.
- Emit and verify test command hash, started marker, finished marker, and test-process exit code.
- Separate patch, dependency/toolchain, collection/build, timeout, runner, and infrastructure failures from behavior results.
- Require testonly behavior-red and gold green with the same intended command identity.
- Seal candidate payload before validation and delivery payload after proof embedding.
- Package all instance-specific repo, patches, scripts, manifests, dependency/toolchain declarations, and proofs together.
- Use fresh per-run/per-group result directories; never reuse summaries.
- Parse per-ID structured results, not aggregate process return codes.
- Harvest through an append-only transaction and activate only after post-harvest direct self-check.
- Count only active production bundles as output.
- Limit real behavior-repair attempts monotonically; infrastructure and pipeline defects never consume them.

## Go Adapter

In addition to the shared kernel, bind and validate:

- exact Go toolchain version and target `GOOS`/`GOARCH`
- `go.mod` and `go.sum` hashes
- module/vendor/cache policy and offline availability
- workspace files and replace directives
- build tags and selected package/test command
- CGO enablement, C compiler identity, and native library dependencies when used
- test binary/package actually selected and executed

Distinguish module download/cache failure, compile failure, test discovery, and behavior failure. A `go test` nonzero caused by missing modules or compilation is not behavior-red.

## C and C++ Adapter

In addition to the shared kernel, bind and validate:

- compiler family, version, target triple, and language standard
- build system and generator versions, such as CMake/Ninja/Make/Meson
- compile definitions, include paths, link flags, and environment
- external library and package-manager lock identity
- generated source/configure artifacts and their reproducibility
- exact test executable or CTest target and working directory
- sanitizer/runtime-loader settings when they are part of the intended verifier

Separate configure, compile, link, loader, test discovery, and behavior failures. Only a successfully built and launched intended test may produce behavior-red.

## Self-Packaging at Initial Generation

Self-packaging is a mandatory first-pass stage, not a harvest afterthought. Before quality validation, generate at least:

- repository snapshot plus revision/tree proof
- gold and test patches
- mounted eval scripts and direct runner
- task and metadata
- instance ID file
- runtime/toolchain manifest
- dependency/build lock or reconstructable declarations
- repair/generation provenance
- candidate bundle manifest
- direct `validate_redgreen.sh`

The candidate seal excludes files that validation must create. After quality and strict red/green, embed quality, strict, and validation proof, then create a delivery seal. Never compare a pre-proof seal to a post-proof bundle as if they should be byte-identical.

For Python, only the base image and validation kit are shared runtime dependencies; conda/seed caches are build-time only. Other language adapters may retain their declared replaceable toolchain/module caches. Instance-specific files and acceptance proof must not live only in staging directories or external ledgers.

## Transactional Harvest and Recovery

Treat production publication as a recoverable transaction with a journal. Recommended phases are:

- `prepared`: candidate and proof identities sealed; destination absent
- `bundle_committed`: atomic bundle rename completed
- `ledgers_committed`: all append-only ledgers record the same transaction and hashes
- `selfcheck_passed`: direct production validation passed
- `active`: catalog includes the bundle

On restart, replay or roll forward an incomplete transaction from its journal. Do not append some ledgers and silently omit others.

If post-harvest direct validation fails:

- mark the transaction `post_harvest_quarantined`
- remove or avoid adding the bundle to the active catalog
- preserve the immutable published candidate and failure proof for audit
- keep the previous catalog pointer active
- do not count the bundle as production output
- route the root cause to pipeline, environment, repository, or verifier repair without inventing a behavior attempt

## Single Attempt Definition

Use one definition in generation, validation, orchestration, skill instructions, and reports.

A real attempt is consumed only when the intended dynamic test command is identity-matched, starts, and either completes with a genuine behavior red/green failure or reaches a candidate runtime timeout. Evidence, quality, packaging, repository, dependency/toolchain, patch, collection/build, infrastructure, approval, capacity, and orchestration failures do not consume a real attempt.

Never let resume flags, retry commands, schema differences, or missing fields decrease, reset, or increment this counter incorrectly.

## Orchestration Before Scaling

A first-pass producer should not scale until a canary completes the entire state machine. Independently review the orchestrator for:

- exact per-ID schema adapters for each stage
- duplicate/missing/extra result rejection
- immutable input and bundle seals
- correct proof-embedding seal transition
- exact production ledger and catalog identity checks
- recoverable transaction journal
- post-harvest quarantine
- monotonic attempt accounting
- crash-safe reservations and resume
- shared global worker slots across concurrent producers
- nonzero process result when selected IDs do not reach valid terminal states

Keep scheduled expansion paused while a critical finding is open. A canary PASS does not override a known orchestrator defect.

## Recommended Architecture

Use a language-neutral coordinator and strict kernel with adapters:

```text
producer
|-- evidence binder
|-- repository identity/materializer
|-- language adapter
|   |-- verifier synthesis
|   |-- dependency/toolchain preflight
|   `-- command/result classifier
|-- self-packager
|-- quality gate
|-- patch preflight
|-- strict red/green runner
|-- proof sealer
|-- transactional harvester
`-- production self-check/catalog activator
```

This keeps correctness rules consistent across languages while allowing Python, Go, C, and C++ to use their native dependency, build, and test systems.
