---
name: swe-multilang-production
description: Operate and improve the Hermes SWE production pipeline. Current scope is Python mounted bundles, with stepfun-ID accounting, bounded semantic repair, identical build/delivery validation, and auditable promotion. Other languages require an explicit new scope.
metadata:
  version: 2.1.0
---

# Python SWE production

## 流式产出原则（信号驱动，强制）
主 agent 不等 subagent 回执批处理。监控信号 = 服务器侧工件落盘状态：
1. **材料落盘**（materials_v4/<ID>/ 三件套+identity）→ 立即 rehearsal→投队列
2. **队列 ready**（batch.json status=ready_for_independent_review）→ 立即派 reviewer
3. **review PASS 落盘**（final_reviews/<ID>.json verdict=PASS）→ 立即 harvest
4. **subagent 退出**（任何原因含 429/timeout/max_iterations）→ **必须立即查盘收遗产+同秒补位维持池子满转（目标 12-15 单元）——用户多次强调的硬性原则，不允许等回执或等批次**。实操：delegate_task(action='list') 清点存活数，低于目标立即补位；退出单元工件（材料/脚本/bundle）用 monitor 扫描归账。
监控工具：材料→rehearsal→投队列自动化脚本统一维护在中央 `/data/huron/swe/swe_dir/scripts/`（勿依赖 /tmp 临时物；历史 /tmp/stream_monitor.py、/tmp/stream_inject.py 已废除）。注意 materials_v4 下有 .tmp 文件需 isdir 过滤；subagent 并发 >13 易触发 requests 级 429，补位小步走。
**交付计数（C6 硬 gate，2026-09-29）**：正式计数只接受 `^stepfun_[0-9]+$` 一级目录；language dirs、accepted IDs、accepted manifest、active catalog 四集合必须相等；delivery 语言目录禁止混入 cache/deps/log/temp 等非 SWE 目录（如 python/20260918_pillow_deps 属 delivery-root 污染，计数程序必须 fail-closed 而非裸 ls|wc）。禁止将 provider overload/基础设施失败计为 SWE attempt。
5. **主动轮询非被动等待**：subagent 中途退出不产生 ASYNC 消息——不能等消息驱动。主 agent 每个 terminal/工具调用周期附带 delegate_task(action='list') 清点存活数。回执消息只是额外信号，不是唯一信号。
6. **硬性下限（用户规定 2026-09-28）**：subagent 存活数**永不低于 10**。任何时点 list 清点 <10 → 立即派新单元补齐，无需权衡。检查节奏：每个工具周期+每次回执处理前后。
7. **外部化 watchdog（已部署 2026-09-28）**：cron job `swe-pipeline-watchdog`（job_id 3d9db90e68fd，每 10 分钟，no_agent 脚本 ~/.hermes/scripts/swe_pipeline_watchdog.sh）自动扫描：待审积压>5/PASS 未 harvest>3/交付总数 3 周期停滞 → 报警注入会话。脚本报警即视为行动令：立即补对应单元。**该机制解决主 agent 长修复期间信号面盲区——报警就是行动令，不是信息**。⚠gateway 未运行则 cron 不 fire——会话开始时 cronjob_manage list 验证 job 存活。

Current user goal (2026-09-24 adjustment): **200 qualified Python deliveries first** as stage-one acceptance (240 as the follow-up target), into `/data/huron/swe/work_20260918/delivery/bundles` (python/), fixed-denominator 40% end-to-end yield and quality requirements unchanged; long-term 1500 unchanged. **One stepfun ID is one output**. Different trajectories with the same issue may count separately, provided each is validated. Exclude officially delivered IDs; use repo/base/issue clusters only to reuse diagnosis and environment recipes. Production authorization is standing — do not treat 'canary-only, stop after handoff' descriptions as current.

## Current execution contract

Read [references/production-v2.md](references/production-v2.md) for exact server paths, commands and result schemas. Read [references/roles.md](references/roles.md) before delegating.

All maintained production scripts must live under `/data/huron/swe/swe_dir/scripts/`; do not create or execute workflow forks in `/tmp`, local temporary directories, or work-root `kit/`. Work roots hold data, logs, plans and results. Bundle runners are hash-bound generated copies of central source, not editable script forks.

The v2 scripts under `/data/huron/swe/swe_dir/scripts/python_pipeline_v2/` are the maintained execution path. The old `work_20260918/staging/*.sh` are forensic inputs, not a source of accepted truth. Never restart old sprint/er8/resident/asm loops to resume v2.

- Count official output only after bundle-local mounted packaging, sealed validation, official harvest and post-harvest checks. v2 `validated` and `accepted` are behavior-stage results; `accepted` remains a legacy compatibility field. `status.behavior_accepted` is not the 1500 delivery count; `official_delivery_count=null` means unmeasured. Preserve all historical rows and report them separately. Combine audited official cohorts by distinct stepfun-ID union. Test cases, retries, directories and VERIFIED log lines never add SWE outputs.
- Preserve old accepted artifacts and evidence. Repairs create a new candidate revision outside delivery. Do not overwrite or delete old bundles, truncate history, or silently count a repair twice.
- Central `bundle_gate.py` performs behavior-stage and relocation checks with the same pinned image. This is necessary but does not certify the final mounted contract. Every final bundle must own its environment/source/base archive and pass the mounted validator without producer caches.
- Verification binds source, gold, tests, runner, dependencies and immutable Docker image ID. Any change invalidates the proof; rerun affected validation and semantic review.
- RED must be an issue-relevant observed behavioral failure. Dependency/import/patch/discovery errors, timeout, signals, and missing markers are failures of setup/validation, not useful RED. The generic-runner classifier only accepts nonzero exits whose output has a Traceback followed by an `^AssertionError(:...)?$` line — so a bare ParseError/ValueError from the target library is REJECTED as test_not_executed (recurring W9b/W12b/W26 defect). Any authored test_repro.py that expects library exceptions in the RED arm must catch them and re-raise as AssertionError (e.g. `except ParseError as e: raise AssertionError(...) from e`); always run the skill's preflight_rehearsal.py before declaring materials ready.
- Derive the smallest executable test command from added/modified `test_patch` cases or the trace-backed issue repro. Prefer exact unittest methods/pytest nodeids; do not default to a whole module/repo. Preserve assertions and relevant parameterized cases. Two cases still belong to one stepfun SWE.
- The target module must import from the patched checkout. Installing a wheel of the project itself can make both arms test an unrelated release; the gate rejects that path.
- Use the exact base commit. Missing hidden fixtures require trace-backed recovery; never substitute a nearby/sibling commit.

## Work allocation

The controller owns catalog, queue, budget, promotion and status. Deterministic scripts execute in bounded batches and record all attempts. GLM 5.3 handles issue/trace understanding, repository environment recipes, focused verifier repair and independent semantic review.

Do not keep subagents busy as an objective. Dispatch only a concrete task with local evidence and an output contract. A 600-second agent budget is for diagnosis or code generation, not waiting on package installation. A model response, `nohup`, or a live PID does not prove useful progress.

Retries require a new, recorded hypothesis. Default v2 implementation allows three validation invocations (currently including setup failures; report executed behavior attempts separately); structural missing-source/missing-gold tasks should go directly to the evidence-recovery queue. Do not require three pointless attempts before deferral. Same fingerprint and same error signature with no change should not be requeued.

## Operating loop

1. Read the handoff and run `status`. Check prepared jobs, leases and last completed attempt time; inspect healthy progress rather than PID count.
2. Use catalog priority and repository clusters. Prefer exact base + recovered test evidence over blind no-diff replay. No-diff inference is provisional until semantic review confirms Python/task identity.
3. Export one ID's indexed evidence. Have the investigator select actual test commands and source edits; unsupported or failed replay events must remain visible.
4. Prepare a candidate with an explicit recipe. Build/cache dependencies by repo, base, interpreter, lockfile hash and architecture. For C extensions, build the project at its exact source commit.
5. Validate the final candidate offline in fresh RED/GREEN/control work directories, under time and resource limits. Inspect full logs and structured phase/status.
6. An independent semantic review confirms issue alignment, behavior evidence, no source oracle and genuine RED. `promote --behavior-only` archives only that behavior proof. For formal output, complete bundle-local environment/base archive/source-tree provenance/seals, relocation without caches, official harvest and post-harvest checks. The v2-to-mounted chain is proven on xsdata stepfun_1438111 (runbook 20260923, post-ingest revalidation PASS); each new repository still needs its own verification pass before formal delivery.
7. Report candidates attempted, accepted stepfun IDs, phase failures, duplicate exclusions, wall time, and model cost when available. Ratios use one clearly stated cohort and denominator, never JSONL event lines.

## Rules superseded after the 2026-09-23 audit

Do not apply these old rules: ever-VERIFIED wins; staging outranks bundle validation; directory existence means delivery; keep at least four subagents forever; clear verdicts then requeue; `(repo,base)` always means the same task; Python 3.13 incompatibility means data is dead; all nonzero exits count as RED; every task needs at least three repair attempts.

Historical examples and conversion percentages are not guarantees. Shared environment fixes must pass a small real-task canary before rollout. Use versioned scripts and hash checks when deploying; do not mutate running shell bodies and assume they reloaded.

## Verified transfer baseline: 20260923.2

Read `references/production-v2.md` for the central 5-ID canary command. All five passed focused testonly/gold/control and relocation; official delivery increment is zero. Hydra 1048885 uses an authored verifier awaiting independent semantic review. Do not turn the five canaries or the historical 12 behavior acceptances into formal output by renaming statuses.

Environment fixes: historical Python 3.10, pinned recipe dependencies, accurate import casing/src roots, and `venv --system-site-packages --without-pip` so ensurepip cannot silently replace the pinned setuptools. For tox retain the recipe SCM version override. Inspect both shell aliases `execute_bash` and `command_exec`. Reconstruct completion requires valid patch hashes and the same plan hash, never only a directory.

Mac relay: bounded download → upload → server hash/archive verification and atomic cache admission → immediate local package deletion. Keep only small receipt metadata. The benchmark is successful, but no production relay CLI is yet delivered; do not advertise it as deployed throughput.


## Generic defect closure loop (mandatory for every defect found by supervision)

For each defect: root cause -> fix in central scripts under `/data/huron/swe/swe_dir/scripts/` -> sync the rule into runtime skills AND the source repo (`huron_skills/skills/hermes`) with equal hashes -> positive AND negative regression (central audits where they exist; temporary fixtures otherwise) -> real-task verification for end-to-end claims -> independent Codex review -> regenerate and revalidate affected old candidates. Record actual file SHA256 and evidence paths per item; never use script comments, file existence, or a `fixed` status field as evidence. Items lacking real results stay open/partial.

Reused central contracts take precedence over new custom manifests: use `repair_static_oracle_sample_trials.py` selfpack functions (`write_candidate_self_package`, `_selfpack_create_exact_git_bundle`, `_selfpack_verify_exact_git_bundle`, `_selfpack_delivery_entries`) for source identity/manifest/runtime declarations; `verify_mounted.py`'s `validate_bundle_patch_contract` / `instrument_test_command` / `validate_existing_command_proof` for command proof (STARTED/FINISHED/COMMAND_SHA256 markers bound to the actually rendered shell command, not `' '.join(argv)`); `mounted_bundle_conversion.py` for sealed-candidate conversion. Cross-check adapter inputs (ID/repo/base/problem/env) against original records and the v2 candidate fingerprint; reject mismatched combinations. Reuse a single shared base archive with immutable image ID (plain-file bytes in each package, hardlinks allowed); never `docker save` per task. Non-Python-prefix commands must prove the executable comes from the bundle env. A first task must pass the official validator, offline independent relocation, harvester dry-run and post-ingest recheck before any batch expansion.


## Controller execution discipline (user directive 2026-09-23 evening)

Scripts do scriptable stages; subagents (fresh contexts, concrete tasks) do model-comprehension stages; the controller runs scripts, schedules, and integrates — never edits central files via ad-hoc string patches from the main loop, never parks subagents as script runners. Repair/maintenance executables belong in the central scripts root (`.incoming` staging + SHA verification); pipeline `tail` must not swallow exit codes. Integration pool: contract engineer / environment-evidence engineer / independent reviewer. After integration: semantic pool 2-4 + review pool 1-2, tuned by queue and results.


## Central release gate & batch circuit breakers (Codex 2026-09-23 evening)

- Deploy mounted-adapter revisions through `/data/huron/swe/swe_dir/scripts/script_release_gate.py` (expected/previous SHA; stale or wrong candidates rejected; auditors' SHAs bound; any failure stops; never deploys or grants `production_ready`; unit pass != production). Expected-SHA comes from the engineer's complete reviewed file. NOTE: the gate's current audits bind only the mounted adapter — other central scripts (env builders, harvesters, batch runners) require their own dedicated tests with same-SHA evidence before deployment, not this gate as-is.
- Batch circuit breakers: host/script errors stop dispatching immediately; repeated setup failures on the same env/repo cluster freeze that cluster; never clear counters or blind-retry with swapped IDs. Semantic failures go to subagents; the controller runs validations.
- Test fixtures and production implementations are separate concerns: never add production fallbacks just to satisfy a missing test fixture (the auditors own their fixtures).
- Base-archive caches need exclusive lock + temp-file write + in-archive config verification (image ID) + atomic rename + content hash; cache data lives under the work root, not the scripts directory. Full metadata/runtime/source seals/hashes are generated in one revision.


## Dispatch schema rule (2026-09-23)

The installed delegate tool reads only `goal` and `context` fields; `content` is ignored silently. Put full task briefs in goal+context, verify the call schema before dispatch, record the context-summary SHA, and steer the complete brief if a child shows signs of missing it. Record deliverable SHAs in external SHA256SUMS/receipt files (a file cannot embed its own SHA256); never accept normalized hashes as sha256sum output.


## Mounted runbook pointer (2026-09-23)

Authoritative executable order and the fully-run xsdata inputs live in `HERMES_MOUNTED_RUNBOOK_20260923.md` (server supervision root + `/Users/huron/Documents/Codex/2026-09-23/n/outputs/`). The xsdata chain passed end-to-end (cold docker, offline relocation, harvest dry-run new_count=1); other repos need their own verification. Codex repairs blocking central scripts directly; the controller prepares materials, drives the queue and executes central commands; fresh subagents do semantic work.


## Stage goal & progressive autonomy (user directive 2026-09-23 evening)

- Stage goal: 200 qualified Python deliveries first (240 later); fixed-denominator 40% end-to-end yield and quality requirements unchanged. From now on Hermes runs the FULL chain per task: verify → converter → relocation → fresh review → harvest → postcheck → counting. Codex repairs blocking central scripts (with regressions + reusable interface) and audits key evidence only.
- Graduated supervision: after Hermes independently completes consecutive qualified loops across DIFFERENT repos with accurate diagnosis and no per-item Codex correction, Codex moves to weak supervision — script-version/new-env/verifier-pattern review plus final counting audit and batch spot-checks. Strong supervision is restored for any affected stage upon identity forgery, static oracle, fake RED, or ledger problems.
- Never stall the queue waiting for dispatches: on a common script bug, preserve exact logs and hand to Codex while continuing material/semantic subagent work on other tasks. env builder central fix SHA 4888b33e2cd7b77e8333e01ae643bcec8cd3336d7890ac1b4e893409d920e9af (2 regressions + real env PASS). Selenium env = stepfun_1080015_py310_codex_r1, selfpack running at $W/selfpack_codex_sel_r4 (do not recreate).
