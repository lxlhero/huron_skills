---
name: openswe-python-oracle-repair
description: Repair Python OpenSWE mounted deliveries whose tests may be static source/gold oracles. Use for large Python verifier-quality repair, trajectory-backed behavior test reconstruction, strict red/green revalidation, and safe harvest back into production.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [swe, openswe, oracle-repair, verifier-quality, python]
    related_skills: [openswe-runtime-builder, openswe-production-stream]
---

# OpenSWE Python Oracle Repair

Use this associated child skill when a Python OpenSWE candidate set or delivery contains tests that may pass only by checking source markers, gold-patch snippets, static files, or other non-behavioral artifacts.

## References

Before generation, validation, orchestration, or harvest, read the references shipped with this skill:

- `references/python-static-oracle-production.md`
- `references/python-bundle-local-delivery.md`

For first-pass production hardening rather than repair-only work, also read:

- `references/first-pass-swe-production.md`

## Contract

- Reconstruct behavior tests from the same instance's original trajectory, issue evidence, observed inputs/outputs, executed tests, or upstream PR evidence.
- Never replace a bad verifier with a source-snippet discriminator, gold-patch checker, marker-file oracle, or stdout-only smoke that does not prove behavior.
- Keep staging roots separate from production. A copied staging bundle is not accepted until dynamic verifier quality, independent patch preflight, strict red/green, and harvest gates pass.
- Python final delivery uses bundle-local environment/source/data plus the declared base image and validation kit. Shared conda/seed roots are build caches only.
- Count only atomically harvested bundles as production output.

## Attempt And Orchestration Rules

- A real repair attempt is consumed only after the candidate has been materialized and verifier/red-green work actually ran.
- Cap real behavior-repair failures at three per SWE unless the user explicitly changes the policy.
- Treat model capacity, SSH transport, approval/tooling, infrastructure, dependency-cache, and stale orchestration failures separately from real behavior-repair attempts.
- Parallelize with Hermes `delegate_task` using at most 3 concurrent leaf subagents; `max_spawn_depth=1`, so nesting repair agents is not allowed. The main session (coordinator) owns SSH, approvals, cache mutation, harvest, and consolidated reporting.
- Reuse an idle subagent slot for the next disjoint batch instead of creating nested work.

## Harvest Rules

- Harvest only through the official repository validation/harvest gate.
- Before append, re-check quality report, strict red/green result, bundle path, manifest row, and accepted-id ledger.
- Do not manually copy staging dirs into production or edit ledgers.
- Report production count separately from staging, attempted, repaired, rejected, abandoned, and unprocessed counts.

## Authorization

Read-only inspection of candidates, staging roots, and quality reports may proceed without extra authorization. Harvest appends, production ledger mutation, and starting repair workers require explicit user authorization first.

If the repair shows that a candidate cannot get a real behavior verifier, classify it as `rejected_static_oracle` or `needs_behavior_test_repair` and leave it out of delivery.
