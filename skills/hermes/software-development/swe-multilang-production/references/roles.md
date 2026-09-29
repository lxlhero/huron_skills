## Repo-Specific Pitfalls (cumulative)
- pandas source build (meson): stash pandas/io during setup (shadows stdlib io); fix PKG_CONFIG_PATH for dead /data/lwj .pc paths (symlink to conda py310 pkgconfig); pin Cython~=3.0.5 per pyproject; `git tag v3.0.0 <base>` on shallow clones (pyarrow integration NameError otherwise). Compiled-tree .so can't ride a git bundle — use sealed-env-style recipe (see stepfun_207613) or container PYTHONPATH build.
- Assertion-form mandate generalizes: ANY expected library exception (ParseError/RuntimeError/ValueError) raised in RED arm must be caught and re-raised as AssertionError (verifier only credits python_assertion_traceback). MONAI RuntimeError, sqlglot ParseError, dvc sys.exit all hit this.
## Process One As It Lands (user directive 2026-09-24 night)
- NEVER wait for a full delegation batch to return before acting. The moment any unit's artifacts appear on disk (final_reviews/*.json, materials_v4/<id>/, queue ready states), verify five-keys and process THAT unit immediately (harvest → postcheck → ledger).
- Dispatch is rolling: as soon as one worker finishes and its output is ingested, backfill the freed slot with the next cluster packet. Slots must never idle waiting for siblings.
- Rationale measured same day: batch-waiting cost ~30% throughput; incremental processing cut harvest latency from batch-drain (~25min) to per-unit (~4min).
## Master/Worker Division (user directive 2026-09-24 evening)
- Master (main agent) NEVER sinks into solving a single SWE task serially. Master does: cohort freezing, dispatch packets (with FULL background+standards+paths — zero-exploration), accounting, and escalation triage only.
- Every pipeline stage that needs model input goes to subagents WITH explicit background + standard + known-pitfalls in the packet (misalignment = rework; spell out the contract).
- harvest + postcheck are delegated to a dedicated "harvest-runner" subagent (deterministic script execution + reporting only).
- Server has 128 cores / load ~9 — raise queue --workers to 12 for new queues; verification is IO-bound docker, concurrency-safe.
## Throughput Optimizations (2026-09-24, empirically validated)
1. Subagent limits raised: child_timeout_seconds 600→1500, max_iterations 50→100 (~/.hermes/config.yaml). One shift now covers 2-ID material work end-to-end; multi-shift re-dispatch waste eliminated.
2. PREFLIGHT contract (mandatory): materials not ready until `bash $S/python_mounted/tools/preflight_materials.sh --id <ID>` prints PREFLIGHT_PASS. Catches the 4 defect classes that caused 71% queue-round waste on 09-24: diff path form (must be b/test_repro.py), hunk truncation/count mismatch, recipe non-standard fields + absolute paths, env_name not materialized. Verified 10/10 PASS on accepted materials, 3/3 defect classes caught.
3. Same-cluster batch dispatch: one material pack (gold/test identical) + per-ID identity + queue fans out per-ID seals. cookiecutter ×3 and sqlfluff ×3 shipped this way; marginal cost per extra ID ≈ 0.
4. Same-cluster review consolidation: ONE reviewer session audits all IDs of a cluster (independent evidence chain per ID, independent manifest fingerprints). Reviewer latency 3× → 1×.
5. Bundle reuse map (server /data/huron/swe/work_20260923_hermes_mounted1/):
   - moto@adeaea7c → moto4_1359066_base_full.bundle; moto@1dfbeed5 → moto2_1dfbeed5_full.bundle (full-history; seed-repo bundles may be orphan-shallow — always `git clone` test before dispatch)
   - sqlglot: sqg_f8d4_base_full.bundle contains full history for MANY bases (33d6e5f2/ba013d6a/3b654f24/0bb40101 all reachable by checkout) — check before minting new bundles
   - dvc@276d499c → dvc_1308165_base_full.bundle; dvc@5d417630 → dvc2_5d417630_base.bundle
   - sqlfluff@665e2a20 → sqlfluff_665e_base.bundle; sqllineage@a5ac784c → sqlf_910883_base_full.bundle; cookiecutter@558f4404 → ck_558f_base.bundle; mypy@a48dd5ad → mypy1_1173018_base_full.bundle
6. Mint bundles server-side from full_seed_repos/local_seed_repos when the base exists with full history (git rev-list --count >1 required; count==1 means orphan — fetch via Mac GitHub clone instead).
7. Env fixes go into NEW copied env (b1_*_py310_m convention: cp -r existing materialized env + python -m pip fix, never edit sealed envs in place). Known-good envs: b1_moto_py310_m, b1_dvc_py310_m (+schema<0.8), b1_sqg_py310_m (+networkx), b1_sqf2_py310_m (click 8.1.7 + dist-info stub w/ entry_points), b1_ck_py310_m, b1_sqlfluff_py310_m, b1_mypy_py310_m, b1_cekit_py310_m.
8. Queue attempt discipline: failed record stays; new attempt = new queue dir R{n+1} (never re-publish same ID into same inbox; publisher refuses replace). Idle-timeout 1800s auto-stops drained queues.
9. Harvest needs review BEFORE run (final_reviews/<ID>.json with canonical five keys); dispatch reviewer as soon as ready_for_review appears — do not wait for batch drain.
10. Throughput model (validated 09-24): materials 630s/ID effective; with 6 slots + preflight first-pass ≥80%: 12-18 IDs/h end-to-end. Bottleneck order: worker compute > defect-reroute > env/bundle fixes > master serial harvest.

## Materials Worker
输出契约最后一步（强制）：四件套落盘后必须跑中央 preflight 并把 PASS 行写进 wave_status：
  bash /data/huron/swe/swe_dir/scripts/python_mounted/tools/preflight_materials.sh --id <ID> [--job /tmp/job_<ID>.json]
FAIL 任何一行 = 材料未完成，继续修到 PASS 才报 ready。preflight 抓四类历史缺陷：diff 路径形态（必须 b/test_repro.py）、hunk 截断/计数、recipe 绝对路径+非标字段、job env 未物化。主控只接受 PREFLIGHT_PASS 的材料入队（一次过率从 29% 拉升的关键）。

# GLM / Hermes role contracts

The controller may run fewer agents than available slots. Concurrency budget (2026-09-24 user directive): **4 fresh semantic workers + 2 fresh reviewers, opened only when work is ready** (no idle agents, no perpetual refill). Semantic workers handle trajectory/gold-test recovery, verifier repair, and env/recipe diagnosis in batches of 2-3 IDs grouped by repo cluster; reviewers are strictly read-only on sealed bundles (read existing strict logs; extra experiments only on independent copies or read-only containers; never execute candidate/delivery env python on the host). The controller itself does NOT do per-item comprehension serially — it only selects material, freezes cohorts, batches scripts, routes results, and serializes harvest (single writer). The audited Hermes global config permits 15 children, max_iterations=50 and child_timeout_seconds=600; these are ceilings, not a SWE concurrency target; do not change global limits for unrelated workflows.

## Controller

Owns task-ID catalog, central script version, SQLite queue, behavior-stage manifests and separately audited official delivery counts. Only the controller owns SSH execution, cache/download jobs and central script deployment; workers propose diffs/recipes as artifacts. Avoid concurrent edits to the central kit. It may perform direct diagnostics and infrastructure fixes. It never writes a success verdict without the evaluator and review. It submits deterministic jobs to the server and collects result files; waiting does not consume a semantic agent slot. Deterministic mounted-chain stages (adapter→source verify→converter→independent copy→offline verify, up to ready_for_review) run through the central 100-ID continuous queue /data/huron/swe/swe_dir/scripts/python_mounted/run_mounted_ready_batch.py (SHA eaf6e69a; --queue INBOX --cohort FROZEN.json --queue-config CONFIG.json --output NEW --workers 4 --stage-timeout 1200 --idle-timeout-seconds 1800 --max-runtime-seconds 21600 --stop-file STOP; full interface in HERMES_BATCH100_RUNBOOK_20260924.md). Individual ready jobs are published ATOMICALLY via python_mounted/publish_mounted_ready_job.py (SHA d8ec0f7; never stream/SCP into the inbox, never republish an ID). Launch rules: mkdir only the parent dir and inbox — never pre-mkdir --output (script requires it absent); capture the real $! in the SAME shell as the background command (not after a (...) subshell); STOP file halts intake and drains. Review/harvest snapshot rule: live ready_for_review.json/ready_groups.json are PENDING-review, never qualified — freeze one publication's group.ids as an immutable review batch, then freeze the reviewed-passed, fingerprint-consistent, not-yet-delivered subset as the harvest list; never feed the growing live ready_ids to the harvester. Same-ID failure is never retried by deleting old inbox jobs or clearing failed/consumed records — STOP-drain the queue, then a NEW inbox + NEW output attempt under the SAME frozen cohort, preserving all failure history. Dispatch packets must be complete and self-contained per ID (issue/trajectory/tool_events/identity absolute paths, exact base/source/env state, central tool commands, output contract) — no 'same six steps' references, no broad directory searches; sessions carry 1–2 same-repo IDs, workers return partial with a first executable artifact or blocking-gap list within ~90s, and the controller keeps active slots filled as sessions expire. Queue output/relocated are CANDIDATES only — the sole official delivery root is /data/huron/swe/work_20260918/delivery/bundles (python/<id>) via the official harvester + postcheck.

## Evidence investigator

Input: one ID (or two to three IDs from the same repository), issue text, full tool timeline with message indices, base identity, previous failure report. Output `diagnosis.json`: ID, phase, hypothesis, cited evidence indices, required files, exact proposed command, and next action (`prepare`, `environment_recipe`, `verifier_repair`, `evidence_missing`, `defer`). No remote scanning of the entire JSONL and no daemon deployment.

## Environment engineer

Input: one repo/base/interpreter cluster and complete build/import logs. Output a versioned recipe, pinned dependencies/wheels, target import roots, timeout budget and one canary result. Never install a release of the target project as a substitute for source. Resolve Python version from the historical project configuration. Do not blindly install the same missing import twelve times.

## Verifier engineer

Input: one issue, exact base and gold, recovered test evidence, diagnostic logs. Output a minimal dynamic verifier patch plus provenance and expected observable failure. It may repair swallowed assertions or choose the correct test, but may not change gold to manufacture green or compare implementation strings/AST against gold. Gold visibility helps understand the defect; assertions must follow the issue and observable behavior.

## Reviewer

Input: immutable candidate fingerprint, original issue, test patch, gold and full gate logs. Use a fresh independent context; the verifier author cannot approve its own verifier. Output `review.json` with `id`, `fingerprint`, `reviewer`, `behavioral`, `issue_aligned`, `no_source_oracle`, `failure_is_issue_related`, `python_task`, and concrete `evidence`. The reviewer does not alter the bundle. `ast.parse` or generated text comparison is not automatically a source oracle: distinguish compiler/decompiler output behavior from reading implementation files.

## Dispatch envelope

Always specify ID, verified server address/port, kit path, work root, source evidence directory, exact permitted edits, acceptance conditions, attempt/time budget, and output path. Do not include passwords or tokens. Each agent writes its result before its final response. Return `incomplete` with saved paths when time is nearly exhausted; do not start a hidden loop.

Review-fingerprint discipline (2026-09-24, from the trino 3822 rework): a reviewer must copy SHA fingerprints programmatically (sha256sum output piped/redirected, never hand-typed) — one dropped character ('cb' lost from a 64-char manifest sha) fails the harvester revision gate with a misleading 'different bundle revision' error. Reviews bind the immutable final manifest + relocation proof only; if a fingerprint mismatch is ever reported, first recompute both sides before assuming a revision change, and route corrections as reviewer-issued incremental fixes of the fingerprint field (never controller-editing a review in place). Reviewers must not run concurrently with an author mutating the same candidate.

Keep roles separate at the judgment boundary; environment reuse and execution belong to scripts. A semantic worker should finish with a concrete artifact, not “started background work”.

## Hermes dispatch mechanics

Role names are instructions in the task prompt, not an assumed public `role` argument. Check the installed `delegate_task` tool schema; unsupported role fields do not create specialist behavior. Start new/fresh contexts for new cohort work instead of resuming v1 agents carrying obsolete status/counting rules.

A dispatch prompt must include: current Python-only scope; one distinct stepfun ID = one SWE; central release20260923.2 and paths; full issue and relevant successful tool timeline; exact test/gold/recipe paths and hashes; allowed artifact output paths; role-specific completion criteria; a bounded budget; current mounted packaging boundary. Explicitly say that v2 behavior `accepted` is not official mounted output.

The investigator returns a complete plan with selected AND ignored edit events (including undo/cleanup and both shell aliases). The verifier engineer targets test_patch cases/repro behavior, not full suites by default. The environment engineer returns Python/package/import-root evidence and a reusable recipe, not an installed release of the project. The independent reviewer reads original issue, final patches and all three logs, cites assertions and observed failure, and does not alter candidates or promote.

When a shared fix works, the controller merges it into `/data/huron/swe/swe_dir/scripts/`, runs a central real canary, and records the new fingerprint. Do not start a worker solely to sleep on a download or to re-run the same failure. If tasks are waiting on missing materials, route them back to investigation instead of keeping agent slots occupied.

Delivery engineer (behavior candidate stable): execute the proven central chain (runbook 20260923) — build_private_python_env → v2_mounted_adapter(selfpack) → verify_mounted → mounted_bundle_conversion → relocation validate_redgreen → fresh review → harvest `--require-bundle-local-env`. Proven on xsdata; each new repo needs its own verification pass.


## Standing production objective (2026-09-23 supervision)

Production waves are 50–100 distinct undelivered stepfun IDs frozen BEFORE recovery (fixed denominator keeping all failures/infra/deferrals; never pad with already-VERIFIED-only picks to inflate yield); material workers claim repo clusters and stream ready entries into the central batch queue continuously — do not re-select a new batch after every 2–5 completions. Controller owns a standing stage target of 200 qualified Python SWE first (240 as the follow-up; delivery root `/data/huron/swe/work_20260918/delivery/bundles/python/`) with locked-cohort end-to-end yield >=40%. Freeze each new production cohort (fixed denominator, including failures/infra) BEFORE recovery/build. Every batch attempt must use a previously-unused output path — never `rm -rf` an old attempt to fake freshness; never overwrite materials while workers are in flight (freeze after worker completion, then hand to batch). Every defect found goes through the generic closure loop (root cause -> central script fix -> dual-location skill sync with hash equality -> positive+negative regression -> real-task verification -> independent review -> affected-candidate regeneration). Record real SHA256 and evidence paths; keep unverified items open. Downloads belong to bounded script polling, not model waiting; contract adaptation work proceeds in parallel.


## Division of labor (user directive 2026-09-23 evening)

- Reliable scripts own every scriptable stage; avoid repeated losses from script defects. Model comprehension stages go to multiple fresh-context subagents with concrete tasks. The controller drives production, runs scripts and schedules — it must not use subagents as script-parallelizers, nor hand-write version-N string patches to central files itself (anchor-mismatch aborts, then auditing the stale SHA, prove nothing).
- ALL executable scripts (including maintenance/repair/deploy helpers) live under `/data/huron/swe/swe_dir/scripts/`; candidate scripts stage in a `.incoming` version dir under that root. The controller compares expected SHAs before/after deployment and stops immediately on command failure — never swallow exit codes through pipe/tail.
- Standard subagent pool while integrating: A script/contract engineer (central adapter + selfpack + verify + converter -> full bridge code + test plan), B environment-evidence engineer (complete bundle env + import/prefix probes; copying one python binary is not an env), C independent reviewer (never reviews its own artifacts). Semantic pool afterwards: 2-4 concrete tasks (investigation / verifier repair / environment diagnosis), independent review pool 1-2. Script concurrency via run_batch --workers and source/env locks — no model slots waiting on downloads.
- Dispatch envelope must include real task IDs, input paths, output paths; results recorded with status. Cohorts freeze before recovery/build. First close the xsdata official-contract loop, then expand.


## Release gate & circuit-breaker rules (2026-09-23)

`script_release_gate.py` applies to the mounted adapter ONLY: expected/previous SHAs bound, stale/mismatched candidates rejected, any failure stops deployment. Every OTHER central script releases on its own basis: reviewed full-file SHA + targeted regression tests + real-run evidence from the chain (no blanket gate). Unit pass != production-ready. Batch runs trip breakers on host/script errors (stop dispatch), repeated same-cluster setup failures (freeze cluster), and never clear counters or swap IDs to keep trying. Cache writes (base archive, env) use lock + temp + verify + atomic rename under the work root. Semantic failures route to subagents; the controller executes validations.


## Dispatch schema discipline (root-cause fix 2026-09-23)

The installed delegate tool reads ONLY `tasks[].goal` and `tasks[].context` — a `tasks[].content` field is silently ignored, leaving the child with nothing but the short goal (observed: child wandered ls-ing home/memory). Always put the full task brief in `goal`+`context`; never rely on `content`. Before dispatch, the controller verifies the call schema and records a SHA of the context summary; on any sign a child lacks its brief (scanning irrelevant paths), steer the full brief immediately. File-header self-SHA256 is impossible (no fixed point of a normal file hash) — record real full-file SHAs in an external SHA256SUMS/receipt; never accept a post-normalization hash as sha256sum output.


## Script-repair division (user directive 2026-09-23)

Codex directly repairs blocking central scripts (env builders, selfpack inputs, harvesters); the controller never hand-patches central code from the main loop nor executes utility scripts outside the central root (`.incoming` staging for new reusable tools, then central paths only). Reviewer erratum: when a reviewer misstates a fact, the controller MUST verify whether it affects the five conclusions; if it does, the review is redone — only if it does not is a correction note sufficient.


## Autonomy ladder (2026-09-23)

Hermes owns the per-task chain end-to-end (verify→converter→relocation→fresh review→harvest→postcheck→count). Codex: blocking script fixes + regression + interface, key-evidence audit. Promotion to weak supervision (version/new-env/verifier review + final count audit + batch sampling) requires: consecutive qualified loops across different repos, accurate diagnosis, zero per-item correction. Identity forgery / static oracle / fake RED / ledger issues → restore strong supervision for the affected stage. Queue never waits idle for dispatch.
