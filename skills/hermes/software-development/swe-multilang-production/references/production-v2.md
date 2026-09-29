# Production v2 runtime

## Audited production-v3 control plane (2026-09-29)

This section is authoritative when it conflicts with historical v2 notes below.
The reusable control plane is installed directly under:

```text
/data/huron/swe/swe_dir/scripts/
```

Published release: `audit-fix-20260929-v1`. Its hash-pinned manifest was
validated as SHA256
`e0a17cb6d60df44b54d6283142e5938b6528e6535e6dac11e6e7feb8ebcb2771`.
The release receipt and history are under
`scripts/.history/audit-fix-20260929-v1/`; do not infer a release from an
unversioned staging file.

Maintained files:

```text
bootstrap_delivery_state.py
counterfactual_gate.py
delivery_count_gate.py
harvest_oracle_repair_staging.py
ledger_event_log.py
production_integrity_gate.py
production_supervision.py
production_throughput_audit.py
publish_production_scripts.py
verifier_quality_gate.py
```

The release passed 74 regressions from the staging bytes and again from the
installed formal bytes. `publish_production_scripts.py` requires an expected-SHA
manifest, takes `.deploy.lock`, saves every prior file in a unique `.history`
directory, writes same-filesystem temporary files, uses `os.replace`, and rolls
back installed files after an exception. A dry-run validates only; it is not a
deployment receipt.

### Start and recovery preflight

```bash
D=/data/huron/swe/work_20260918/delivery
A=<new-process-artifact-directory>

python3 /data/huron/swe/swe_dir/scripts/production_integrity_gate.py \
  --production-root "$D" --output-json "$A/integrity.json"

python3 /data/huron/swe/swe_dir/scripts/production_supervision.py preflight \
  --delivery-root "$D" --output "$A/preflight.json"
```

Both commands must exit zero and report `ok=true`. They reconcile exact sets,
not counts alone. Any incomplete transaction, illegal bundle directory,
language mismatch, missing/tampered evidence, stale derived view, or replay
disagreement freezes all mutation.

On startup, inspect `.state_transactions/*/journal.json`. Recovery is handled by
`ledger_event_log.recover_incomplete_transactions()` under the state lock:
before durable evidence/event, restore the `before` views and bundle locations;
after evidence or event is durable, finish forward without duplicating events.
Never delete a journal, rewrite history, or invent a catalog to make checks pass.

Legacy delivery bootstrap is a one-time migration only:

```bash
python3 /data/huron/swe/swe_dir/scripts/bootstrap_delivery_state.py \
  --production-root "$D" --reason '<reason>'
# Inspect the dry-run result, then:
python3 /data/huron/swe/swe_dir/scripts/bootstrap_delivery_state.py \
  --production-root "$D" --reason '<same reason>' --apply
```

Bootstrap events establish prior accepted state and never count as new delivery
velocity. If the event log already exists, do not bootstrap a second history.

### Verifier admission

`verifier_quality_gate.py` binds the review to all bundle-owned `.py`/shell
verifier scripts outside source/runtime directories, including second-level
helpers. It recognizes `/bundle/...` paths, root-level `test_*.py`, and simple
data flow from source-file reads into later assertions. Source/gold oracles are
hard rejects; all remaining candidates require model semantic review.

Semantic review is not keyword classification. Trace the executed call path from
the public issue entrypoint to the assertion and ask whether an intentionally
wrong implementation would pass. Two known failure patterns are mandatory
regressions:

- `stepfun_1195343`: checking only `identify_payload` booleans misses public
  receive parsing and the complete private-JSON receive path.
- `stepfun_37834`: directly calling an auth mixin admits a global unsigned-auth
  bypass because it never exercises Cognito `GetId` or a protected unsigned
  negative control.

For every high-risk suspect, store two executed arms under the candidate bundle:

```text
validation/counterfactual/
  non_fix.patch
  non_fix.log
  non_fix.proof.json
  equivalent_fix.patch
  equivalent_fix.log
  equivalent_fix.proof.json
```

`counterfactual_gate.py` requires real files and hashes, one execution marker and
one exit marker per log, identical canonical command/image across arms, distinct
patches, nonzero non-fix, and zero equivalent-fix. The semantic review references
these bundle-local artifacts; it may not choose an external artifact root.

### Promotion, quarantine, and counting

Run validation and semantic review in staging. Formal promotion uses
`harvest_oracle_repair_staging.py` with explicit canonical `--language`; the
legacy unpartitioned mutating path is disabled. The harvester must call the
activation transaction so bundle ownership, all active views, and activation
events commit or recover together.

To remove an invalid accepted SWE, write a model-readable audit artifact inside
the delivery, hash it, then call `ledger_event_log.quarantine()` with the
delivery-relative path and SHA. The transaction moves the bundle under
`quarantine/<language>/<id>`, removes the ID from every active view, appends
tombstone evidence, and appends a bound tombstone event. Never delete a bundle or
edit five ledgers by hand. Reactivation requires a newly prepared bundle and the
normal activation transaction; `reactivate()` intentionally fails.

Official count:

```bash
python3 /data/huron/swe/swe_dir/scripts/delivery_count_gate.py \
  --delivery-root "$D" --report "$A/count.json" --json
```

The wrapper emits `total=null` on any integrity failure. Throughput:

```bash
python3 /data/huron/swe/swe_dir/scripts/production_throughput_audit.py \
  --queue-root <frozen-cohort-queue-root> --delivery-root "$D" \
  --window-hours 48 --output "$A/throughput.json"
```

Only committed activation event timestamps count. Bootstrap, bundle mtimes, and
filesystem arrival do not.

### Supervised 150-ID expansion

Resume Hermes session `20260918_111501_0ddc6d`. Freeze exactly 150 previously
undelivered IDs and record their ordered IDs plus source snapshot hash before
dispatch. Q57, Q50, and R10 are excluded. Wave sizes are selected per the
current request and observed risk. The following is a default playbook, not a
hard-coded requirement:

1. Use a small canary when scripts, runtime manifests, repositories, or
   environments are new or recently repaired.
2. Increase the next wave only after the chosen canary report is accepted; a
   shared defect freezes the affected lane regardless of wave number.
3. Continue to the frozen 150 when evidence supports it. Keep one ledger writer.
   Repo-affinity microbatches may build concurrently, but promotion is serialized
   through the official transaction.

This batch separately requires 10 no-mount self-contained image builds with
RED/GREEN. They may be sampled across the frozen cohort and do not dictate the
first wave size.

For all 150, RED/GREEN execution coverage is 100%; every accepted item has a
semantic review artifact; Codex independently model-audits at least 35% of the
cohort. Do not replace failed or pending IDs. Every 15 minutes report queue depth
per stage, completed/failed/pending within the frozen denominator, committed
activation rates for 15/60 minutes, p50/p95 stage time, and classified failure
counts. Provider overload and setup failure are operational failures, not SWE RED
or accepted throughput.

Server: `root@180.184.86.2`, SSH port `35120`; credentials supplied at runtime.
Kit: `/data/huron/swe/swe_dir/scripts/python_pipeline_v2/`.
Work root: `/data/huron/swe/work_20260923_glm_v2/`.
Current transfer: `/data/huron/swe/work_20260923_glm_v2/GLM_WORKFLOW_TRANSFER_20260923.md`.
Central release: `20260923.2`; entrypoint map: `/data/huron/swe/swe_dir/scripts/README.production.md`.
Use the central scripts only. New data-only canary root: `/data/huron/swe/work_20260923_central_canary5/`.
Raw source: `/data/huron/swe/swe_dir/data/stepfun_subset2_agent_gt_65536.jsonl`.
Inventory input: `/data/huron/swe/work_20260918/staging/inventory.jsonl`.
Official exclusion: `/data/huron/swe/swe_dir/delivery_list/delivered.jsonl`.
Old artifacts: `/data/huron/swe/work_20260918/delivery/bundles/`.

Do not reuse production v1 DB or edit it. The new `state.sqlite3` uses WAL, transactional leases, append-only events, and one accepted row per stepfun ID. Run roots are outside bundle directories; candidate revisions are immutable during evaluation.

## CLI

Use `python3 <kit>/swe_v2.py --root <work-root> <command>`.

- `run_batch.py --root <root> --max-jobs 10 --workers 2` (separate script): bounded prepared-job execution; it never creates semantic reviews or promotes automatically.
- `status`: catalog/jobs/accepted/expired leases, last completed validation time, attempt and distinct-ID counts, latest failure phases. A stalled lease requires diagnosis before recovery. `validated` still needs an independent semantic review; `accepted` / `behavior_accepted` count only behavior-stage archives, not official mounted output. `official_delivery_count=null` explicitly leaves the formal count unmeasured.
- `shortlist --limit 30`: IDs ordered by test evidence, with repository cluster keys. Low-priority inference is not proof of language.
- `evidence --id <id> --source <raw-source>`: O(1) indexed extraction; emits exact trajectory, tool events and issue.
- `inspect_task.py --root <root> --id <id> --output <packet.json>` (separate script): read-only evidence packet with both `execute_bash` and `command_exec`; the original shell commands are not executed.
- `reconstruct.py --root <root> --id <id> --plan <reviewed-plan.json>` (separate script): replay selected successful editor events from exact base; each other editor event needs an explicit ignore reason. Shell calls are reviewed, never executed. Publishes completed gold/test patches atomically, with reconstruction hashes. A failed directory is not a skip condition; completion must match the reviewed plan and patch hashes. `external_test_recovery` is explicit gold-only recovery requiring separate test provenance, not automatic acceptance.
- `prepare --id <id> --materials <dir> --recipe <json> [--test-patch <diff>]`: exact upstream source, gold/test, wheels and explicit recipe into a fresh candidate. Materials may be an old bundle or a reviewed extraction directory. Existing `task.json` identity must match the catalog.
- `validate --id <id> --timeout 600 --cpus 2 --memory 4g`: offline three-arm validation and structured evidence. Calling without ID claims one ready task transactionally.
- `promote --behavior-only --id <id> --review <json>`: only validated fingerprint with semantic review; append behavior-stage archive, export a versioned manifest. Without `--behavior-only` the command refuses before opening the DB. This command does not certify the mounted delivery contract.
- `catalog --source <raw> --inventory <inventory> --delivered <official-jsonl>`: source indexing. It does not mark legacy outputs accepted. Use a separate explicit legacy audit when migrating them.

A recipe includes `image`, `pythonpath` (relative source paths), `target_modules`, `test_command` (argv array), `expected_failure_patterns` (issue-specific), `install_project`, `build_timeout`, `test_timeout`. Build offline from captured dependencies. A missing wheel is `dependencies` failure, not RED. Keep interpreter and package constraints in the recipe/materials; never run a generic latest-package loop.

Behavior-stage archived artifacts (historical directory naming) are under `delivery/bundles/python/<id>` and proof files under `delivery/proofs/<id>`. `delivery/current.json` points to one complete manifest snapshot. Acceptance truth is the database/manifest plus bound proof, not a prefilled metadata flag. Bundle `run_redgreen.sh` uses its shipped `bundle_gate.py` and pinned image ID.

The v2 canary currently uses per-repository dependency images. It does **not** implement the full Python mounted ownership contract. Final bundles require their own environment, exact repository/base/tree proof, base archive bytes, source/fixtures, relative hash-bound validation kit, manifests/seals, offline relocation without producer caches, official harvest and post-harvest verification. The five central canaries contribute zero formal outputs. Preserve historical accepted artifacts and report them as a separate behavior cohort until formally requalified.

Mounted pipeline status (runbook 2026-09-23, HERMES_MOUNTED_RUNBOOK_20260923.md): the xsdata chain (build_private_python_env → v2_mounted_adapter → selfpack → verify_mounted → mounted_bundle_conversion → validate_redgreen relocation → fresh review → harvest dry-run/ingest) has been ACTUALLY RUN end-to-end and passed, including cold-docker archive load in an isolated namespace and offline red/green. Other repositories still require their own per-task verification — do not generalize xsdata's pass. Existing official harvester: `/data/huron/swe/swe_dir/scripts/harvest_oracle_repair_staging.py` (`--language python --require-bundle-local-env --semantic-review-root`, dry-run first, unique run labels, post-ingest revalidate from the official target). Never fabricate seals, manually copy into production, or insert accepted rows. Division of labor (user directive): Codex directly repairs blocking central scripts; Hermes controller drives the queue, prepares materials, and executes central commands; fresh subagents handle issue/trace comprehension, verifier repair, and independent review. Do not resurrect the B2/v9 self-made packaging routes.

Promotion copies logs with hashes. A directory without the matching DB row requires reconciliation, not overwriting. A changed bundle must be prepared as a new candidate. Final delivery cannot depend on producer caches or preloaded per-task dependency images.

The user has authorized standing continuous production (240 qualified Python SWE, locked-cohort yield >= 40%). After any repair, run representative regressions first (false-green/environment failures must be rejected), then continue bounded cohorts with per-cohort reporting. No unbounded experimental workers.

## Reproduce the successful focused workflow

```bash
KIT=/data/huron/swe/swe_dir/scripts/python_pipeline_v2
python3 "$KIT/run_canary.py" \
  --source-root /data/huron/swe/work_20260923_codex_canary5 \
  --root /data/huron/swe/work_20260923_glm_canary_NEXT \
  --workers 2 --timeout 240
```

Use a new root each time; add `--ids 1688677` for the tox check. This reads prior materials as data and runs only central code. It never promotes. Results: `<root>/canary_results.json`, per-ID proofs and full logs. Recipes are central `recipes/canary5/<stepfun_id>.json`; environment Dockerfiles/freeze records are `environments/canary5/`.

Focused scopes: Selenium1080015 two new headless-remote methods; LightStep1277965 inject/propagation two nodeids; tox1688677 diff/recreation two nodeids; xsdata1438111 one trace e2e script; Hydra1048885 one authored behavioral verifier, independent review pending. They remain five SWE regardless of case counts.

Python310 avoids historical Python313 incompatibilities. `container_eval.py` creates `venv --system-site-packages --without-pip`: default ensurepip would overwrite pinned setuptools69.5.1 with79 and break editable installation. Keep tox's `SETUPTOOLS_SCM_PRETEND_VERSION=4.0.0a1`. Do not fix this by installing a release of tox or the target project. Source and import roots are recipe-specific.

Build networking and test networking are separate: cold package builds may use the observed working host network; validation is always network none. Share environments only across matching repo/base/Python/arch/dependency identity. Prefer warm source caches and bounded parallel deterministic jobs over assigning model agents to wait for downloads. Outer reconstruction budgets must cover source-lock and download budgets; do not restore the old880s cutoff or broad pkill loops.

## Mounted adapter defect rules (20260923 supervision, D1-D6)

- The mounted runner generator must expose ONE shared `render_eval(cmd_argv, mode)`; generators and regression audits call the same function. Never inject the test command as a printed/echoed string — the rendered script must execute it and echo only the real test rc as `OPENSWE_EXIT_CODE`. Every adapter change runs an exit-7 must-execute probe (both modes) before merge.
- Infra/setup failures (cd, clone, checkout, patch apply, missing env) emit `OPENSWE_INFRA_SETUP_FAILED=<reason>` + `OPENSWE_TEST_EXECUTED=false` and exit nonzero WITHOUT any `OPENSWE_EXIT_CODE` marker (no fake test result). They are never behavioral RED. The runner never deletes a caller-provided path: the testbed must be a fresh exclusive directory under WORK_ROOT, realpath-normalized with parent-chain checks.
- Git identity comes only from a real commit object (seed-root clone, exact fetch of the base SHA, or a pre-staged full-history bundle). Never `git init && commit` a fabricated HEAD. Codeload tarballs have no git objects.
- Bundle-local env fingerprint covers regular files AND symlinks (resolved target recorded); ANY symlink escaping the env root — relative `../`, absolute, prefix-collision, or broken — is a hard error (use `link.resolve(strict=True).relative_to(root)`). Record file modes. `docker save` failure is fatal (no null-archive success). Command injection uses `shlex.quote` per element.
- The bundle manifest seals the full payload: git bundle sha, both patch shas, env tree sha, base-image archive sha, full problem statement (no "see v2 evidence" placeholders).
- exec-embedded assertions DO propagate at runtime; the AST quality screen is merely limited. A verifier whose assertions live inside an exec string must pass dynamic failure-propagation testing plus semantic review. Do not force-rewrite merely to satisfy an AST classifier, and never alter tests just to please a gate.


## Material-collection rules (runbook 2026-09-23)

- New-batch selection first excludes IDs against the official `delivery/accepted_swe_ids_latest.txt` AND the officially delivered list; v2 behavior-accepted ≠ new formal delivery; never overwrite old packages. Historical curated canaries are not an end-to-end 40% sample. Distinct stepfun IDs count once each; retries/test counts/versions of the same ID add nothing.
- Material inventories record real server system datetime (never hand-written); items not yet searched are marked `not_searched` (never "confirmed missing"). Issue examples referencing `/tmp` etc. are preserved verbatim in problem_statement — they are examples, not runtime dependencies.
- Frozen cohorts (central `production_supervision.py freeze`) before recovery/build keep failures/infra/pending in the denominator. Env/source build materials are reused only on proven-compatible identity; every final package still carries its full payload. Base archive is shared; never docker-save per task. Common script failures stop that task class and go to Codex for direct repair — no ID-swapping retries.


## 100-ID continuous batch queue (central, 2026-09-24)
- Entry: /data/huron/swe/swe_dir/scripts/python_mounted/run_mounted_ready_batch.py (SHA eaf6e69a) with --queue INBOX --cohort FROZEN.json --queue-config CONFIG.json --output NEW --workers 4 --stage-timeout 1200 --poll-seconds 3 --idle-timeout-seconds 1800 --max-runtime-seconds 21600 --stop-file STOP. CONFIG carries raw_jsonl + base_image_archive (+ validation_kits, published central kits only). Full interface: HERMES_BATCH100_RUNBOOK_20260924.md.
- Publishing: python_mounted/publish_mounted_ready_job.py (SHA d8ec0f7) publishes one complete ready job atomically ({id,candidate,identity,git_bundle,conda_root,env_name,validation_kit}); env pre-materialized, materials frozen (no author edits after publish). Never stream/SCP into the inbox; republishing an existing ID is refused.
- Launch discipline: mkdir only the queue parent dir + inbox; --output must NOT pre-exist (script creates it); record the real $! in the same shell as the background launch; verify liveness via ps (never pgrep -f patterns that match the launching shell); STOP file stops intake and drains in-flight.
- Semantics: ready_for_review.json / review_groups.json refresh live and mean PENDING review, not qualification. Controller freezes one publication's group.ids as an immutable review batch for independent reviewers; then freezes the reviewed-passed, fingerprint-consistent, undelivered subset as the harvest list (grouped by kit) for the official harvester (dry → formal → postcheck from the official root). Never harvest directly from live/growing ready_ids. Same-ID failure is never auto-retried — fix and open a controlled new attempt, keeping the wave denominator and failure history.
- Official delivery root (sole): /data/huron/swe/work_20260918/delivery/bundles/python/<id>. Queue outputs are candidates only.
- Defect-closure ledger (root cause → central SHA → regression → real evidence → dual skill SHA → independent review): scanner linearization e4c7270288db55751123f1fdeb21039b9ff3cdb75c3f34d52133113af6c18aba (20MB index re.search ~249.7GB → 0.365s, 10 tests + independent review); while-read missing trailing newline (wave100 missed last ID, fixed by full-set reconciliation + central prepare_wave_evidence.py); pgrep -f self-match false RUNNING (use ps-verified liveness, never sleep on it).

## Stage goal 200 (user directive 2026-09-23)

Target: 200 qualified Python deliveries before the 240 goal; fixed-denominator ≥40% end-to-end yield retained. Hermes executes the full per-task chain independently (verify→converter→relocation→fresh review→harvest→postcheck→count); Codex handles only blocking script repairs and key-evidence audits, with supervision tapering (strong → version/env/verifier review + count audit + batch sampling) as Hermes demonstrates consecutive independent qualified loops; regressions (forgery/oracle/fake-RED/ledger) restore strong supervision per stage. Never idle the queue waiting for external dispatch.
