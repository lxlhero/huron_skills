# Python Static-Oracle Production Repair

For Python mounted production, apply [python-bundle-local-delivery.md](python-bundle-local-delivery.md). Shared conda/seed paths in build examples are staging caches, never final runtime dependencies. Each SWE owns its environment, source/Git, data and local base archive; only the base runtime and version-bound validation kit are shared. Explicit image-only requests and other-language adapters remain separate.


Use this reference when converting a large Python OpenSWE candidate set from source/static oracles into deliverable behavior verifiers. It is a fail-closed production workflow, not a best-effort filter.

## Outcome and Accounting

Count an SWE as produced only after it is present in the production `bundles/<instance_id>` directory through the harvest gate. Generation candidates, quality-gate candidates, red/green passes in staging, repair attempts, and allowlists are separate counts.

Report at least:

- production bundle count
- newly harvested count for the current run
- generation candidates and rejections
- quality accepted and rejected
- strict red/green passed and failed
- infrastructure requeues
- real attempt failures and abandoned-after-three IDs
- unprocessed IDs

Never mix staging candidates into production `bundles/` to make progress appear larger.

## Authoritative Inputs

For each instance, bind every repair to:

- the original trajectory record for the same instance ID
- repository name and full base commit
- original gold patch
- the exact behavior test content or reconstruction algorithm
- trajectory message indexes that establish the test and executed command
- observed base and gold outcomes for the same normalized command

A test reconstructed from another instance, an intermediate patch, source text, a gold marker, or an unexecuted suggestion is not valid evidence.

Before a canary or batch starts, seal an input package containing ID list, raw trajectory subset, evidence rows, reconstruction payloads, and a manifest with file SHA-256 values. The ID sets must be unique and identical across required files. Missing or conflicting evidence blocks the ID.

## Required Stage Order

Run these stages in order and persist disjoint outputs:

1. Generation: rebuild a behavior verifier in an isolated bundle.
2. Quality: reject static/source/gold-marker or unknown verifiers.
3. Repository identity: prove the exact declared base commit and content.
4. Patch preflight: test and gold patches must apply independently on clean snapshots.
5. Strict red/green: intended test runs; testonly is behavior-red and gold is green.
6. Proof sealing: bind results to bundle, patch, command, environment, and repository hashes.
7. Harvest: perform a fresh validation and atomically append only eligible bundles.
8. Production self-check: run the harvested bundle's direct validation entrypoint.

Do not skip a stage because an older log says PASS. A changed bundle invalidates prior downstream proof.

## Dynamic Verifier Rules

A behavior verifier must execute externally observable behavior and contain a positive runtime failure mechanism, such as a Python `assert`, a known assertion API, an uncaught expected exception check, or an explicit process exit based on computed behavior.

Reject verifiers that:

- read implementation source files to decide pass/fail
- inspect gold patch text, expected additions/removals, or marker strings
- only print PASS/FAIL while always exiting zero
- depend on stdout string matching as the oracle
- test an unrelated regression or a behavior both base and gold satisfy
- use different normalized test commands for base and gold evidence
- fail because of import, collection, syntax, patch, solver, service, mount, or runner errors
- are merely `unknown_non_static`

When converting a print-only trajectory test, rewrite its actual boolean condition into an assertion or process exit. Do not assert that the output contains the words PASS or FAIL.

Use unified-diff-aware parsing and Python AST analysis when checking test patches. Scan only added Python code; ignore diff headers, comments, and string literals. Recognize normal `assert`, unittest/pytest assertions, NumPy testing assertions, and explicit `AssertionError` patterns. Keep the source/gold-marker denylist active after positive assertion detection.

## Repository Identity and Materialization

A bundle must use the exact full base commit declared by task metadata.

For a normal Git checkout, require:

- real HEAD equals base commit
- clean worktree
- tree OID matches the declared/attested tree

For an archive bundle without `.git`, require:

- `.swe_base_commit` equals base commit
- repair provenance records the exact resolved commit, seed tree OID, archive SHA-256, and materialization method
- the seed repository contains the exact commit object
- a freshly generated archive matches the recorded digest
- every path, Git mode, symlink target, and blob/content identity matches the seed tree

A temporary `git init` may be used only inside an independent runtime copy to support `git apply`; it cannot establish or fabricate base identity.

If a seed commit is absent, route the instance to infrastructure requeue. The coordinator may fetch the exact SHA into the shared seed cache. Do not ask each subagent to fetch it. Network, mirror, capacity, or missing-seed failures do not consume an SWE repair attempt.

Support old Git safely. If `git rev-parse --show-object-format` is unsupported or is echoed literally, infer SHA-1 only when all relevant commit/tree OIDs are exactly 40 hexadecimal characters. Otherwise fail closed.

## Strict Red/Green Contract

Testonly must:

- start from an independently verified clean base snapshot
- apply only the test patch successfully
- emit patch-preflight success
- execute the intended command
- emit matching command SHA-256 and test-started/test-finished markers
- return a present nonzero test process exit code caused by target behavior
- have no timeout, environment, collection, patch, or infrastructure failure

Gold must:

- start from a separate clean base snapshot
- apply the gold patch, then the same test patch, both successfully
- execute the exact same command and command hash
- return test process exit code zero
- have no timeout or non-behavior failure

Recommended structured markers are:

- `OPENSWE_PATCH_PREFLIGHT_STATUS=passed`
- `OPENSWE_TEST_COMMAND_SHA256=<sha256>`
- `OPENSWE_TEST_STARTED=1`
- `OPENSWE_TEST_FINISHED=1`
- `OPENSWE_EXIT_CODE=<test-process-rc>`

Patch, setup, import, collection, and runner failures must use distinct fields and must not synthesize an exit code that can be interpreted as behavioral red.

## Attempt Accounting

Allow at most three real repair failures per instance.

Consume one attempt only when:

- the intended dynamic test started and completed with valid command proof, but strict red/green failed for behavior; or
- the intended candidate test started and reached a candidate runtime timeout

Do not consume an attempt for:

- generation or quality rejection
- missing trajectory evidence
- seed, repository identity, or patch preflight failure
- missing dependency, solver, collection, or test-path failure
- Docker/image/mount/runner failure
- SSH, network, permission, approval, rate limit, 429, or model-capacity failure
- an orchestration or script bug

After the third real failure, mark `abandoned_after_3_attempts`. Resume logic must never reduce or bypass the counter.

## Self-Contained Bundle Contract

Each delivered `bundles/<instance_id>` directory should contain everything specific to that SWE. The only shared executable component may be the workspace `validation_kit`. Shared conda and seed repositories are build caches only. Materialize the complete environment, source/Git data and ordinary local base archive into every Python bundle; external symlink/cache dependencies are forbidden.

Required bundle content includes:

- `repo/` with base identity sentinel/proof
- `gold_patch.diff` and `test_patch.diff`
- mounted testonly and gold eval scripts
- `run_mounted_eval.sh`
- `task.json` and `metadata.json`
- `instance_id.txt`
- `repair_provenance.json`
- `runtime_manifest.json`
- `bundle_manifest.json`
- reconstructable dependency declarations/lock and source hashes
- quality report and strict red/green result after harvest
- validation proof bound to current bundle hashes
- executable `validate_redgreen.sh`

`validate_redgreen.sh` must resolve the bundle from its own location, call only the relative workspace validation kit, and store results under `bundle/validation/`. Final execution must select the bundle-local environment at its recorded fixed container prefix and the local source/Git payload. Image overrides must retain the declared image identity. External conda/seed cache overrides and fallback searches are build-time conveniences only and must not affect final validation.

A production bundle should support:

```bash
cd bundles/<instance_id>
./validate_redgreen.sh
```

The bundle manifest must use relative paths and file hashes. Staging paths, temporary run paths, and external ledgers must not be required to execute or audit the delivered bundle.

## Harvest Rules

Only the harvest program may mutate production bundles or append production ledgers.

Harvest must:

- run a fresh quality and strict red/green validation
- require `ok=true` and `harvest_eligible=true` for the same current bundle seal
- verify repository identity, both preflights, behavior-red testonly, and green gold
- use a new run-label/group-specific results directory
- fail if that directory already exists or its summary is absent
- parse per-ID structured results, not a subprocess's aggregate return code
- write quality, strict result, validation proof, and final manifest into the bundle
- strip staging/run absolute paths from delivery dependencies
- acquire production append locks
- copy through a temporary directory and atomically rename
- never overwrite a conflicting production bundle
- append ledgers only after the atomic bundle commit

Legacy and external-diff groups must never share result or summary paths.

## Batch Orchestration and Agents

Use at most four top-level repair agents and prohibit nested agents. Keep agents on disjoint responsibilities such as generator repair, evidence reconstruction, semantic review, and strict/harvest auditing.

The coordinator owns all SSH, network, permission, approval, shared-cache mutation, and production harvest operations. Subagents work on local broker artifacts and report requests to the coordinator. Retry transient 429 or model-capacity errors; do not treat them as agent death or an SWE attempt.

Before activating a batch orchestrator, independently review it for:

- per-ID strict result parsing
- correct worker/bundle/harvest path levels
- nonzero exit when selected IDs do not reach valid terminal states
- immutable monotonic attempt ledgers
- resume locks and crash reservations
- generation/quality fail-closed set invariants
- command/patch proof identity
- bundle seals across quality, strict, and harvest
- no eval regeneration TOCTOU
- global worker slots across concurrent orchestrators, capped at four
- corrupted ledger rows causing hard failure

Do not enable periodic expansion merely because a canary passed. The user controls whether scheduling is active. Keep a paused automation paused until explicitly resumed.

## Canary and Freeze Protocol

Before scaling:

1. Produce one isolated candidate from original trajectory evidence.
2. Pass dynamic quality, exact repo identity, both patch preflights, and strict red/green.
3. Package it as a self-contained bundle.
4. Run its `validate_redgreen.sh` with no per-instance command arguments.
5. Harvest through the production gate.
6. Run the same direct validation from the production directory.
7. Independently review the batch orchestrator and close every critical finding.
8. Freeze script versions/digests used by the run.

If later failures reveal a generator, validator, or orchestrator bug, classify them as pipeline defects, fix the pipeline in isolation, and repeat the canary. Do not consume candidate attempts or continue scaling with a known defect.

## Reference Implementation Roles

A workspace may provide scripts equivalent to:

- `repair_static_oracle_sample_trials.py`: trajectory-backed generation and self-packaging
- `verifier_quality_gate.py`: dynamic verifier quality classification
- `verify_mounted.py`: repository identity, patch preflight, and strict red/green
- `harvest_oracle_repair_staging.py`: fresh admission and atomic production append
- `run_strict_python_swe_repair_batch.py`: resumable state-machine orchestration

Treat names and locations as workspace-specific. The contracts above are authoritative; a script is not trusted merely because it has one of these names.

## Transaction and Recovery Clarifications

Treat self-packaging as an explicit stage before quality validation. Create a candidate payload seal that excludes validation outputs. After quality and strict red/green proofs are embedded, create a separate delivery seal; do not require the pre-proof and post-proof bundle hashes to be identical.

Use one attempt definition throughout the pipeline: only an identity-matched intended test that starts and has a genuine behavior failure, or an intended candidate test that starts and times out, consumes an attempt. All proof, schema, packaging, repository, dependency, patch, collection, infrastructure, approval, capacity, and orchestration failures are non-attempt routes.

Production publication must use a transaction journal that binds the bundle, every append-only ledger entry, proof hashes, and active catalog update. Recover incomplete transactions deterministically after a crash. Do not treat bundle rename plus unrelated ledger appends as fully atomic without a journal.

Run direct validation after publication but before active-catalog admission. A post-harvest failure moves the transaction to `post_harvest_quarantined`, preserves evidence, keeps the previous catalog active, and removes the bundle from production counts until recovery succeeds.

For guidance that applies during initial generation, including Go, C, and C++, read [first-pass-swe-production.md](first-pass-swe-production.md).
