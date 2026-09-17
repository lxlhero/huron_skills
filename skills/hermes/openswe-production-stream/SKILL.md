---
name: openswe-production-stream
description: Operate the ongoing OpenSWE production stream on a lab workspace. Use for inspecting progress ledgers, managing wave batches, harvesting validated bundles, and keeping append-only production state consistent without rewriting accepted outputs.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [swe, openswe, production-stream, harvest, wave-batch, operations]
    related_skills: [openswe-runtime-builder, openswe-python-oracle-repair]
---

# OpenSWE Production Stream

Use this associated child skill when the user asks to continue or inspect an existing OpenSWE production stream, wave batch, repair queue, remote progress ledger, or harvest process. This is an operations skill, not the default first-pass builder.

## References

The reference docs for this skill are kept only in the parent skill `openswe-runtime-builder` (single source of truth — no duplicated copies). Load that skill and read from its tree:

- `references/pipeline_stages.md`
- `references/openswe_pipeline.md`

If the stream involves multi-language mounted delivery, also read:

- `references/openswe_multilang_delivery.md`

If the stream involves Python static-oracle repair queues, use `openswe-python-oracle-repair` as the repair policy source.

## Operating Pattern

1. Read the latest project progress ledger first, then inspect only the active wave/batch paths it names.
2. Before appending, confirm consistency across verified ids, manifests, latest accepted ids/manifests, failed-latest files, and bundle directories.
3. Avoid concurrent production ledger writers. Acquire the production append lock before harvest work that can mutate accepted output.
4. Append only through the validation/harvest gate. Never manually copy bundle directories into production or edit ledgers.
5. Before refreshing latest pointer files, create timestamped backups and preserve every existing accepted id.
6. Keep `failed_swe_*_latest` empty unless real failures are intentionally recorded.
7. Update the progress ledger after material steps with concrete counts, labels, paths, discarded ids, and post-harvest checks.

## Safety Invariants

- Already accepted SWE outputs are durable assets. Do not delete, rewrite, prune, rebuild, overwrite, or clean up existing production bundles.
- Do not remove existing verified ids or manifest rows.
- Do not run global Docker prune.
- Do not persist SSH passwords, tokens, AK/SK, gateway credentials, or `GITHUB_TOKEN`.
- Long-tail validation/env items may be discarded only when the user has authorized flow-first production and the tail is blocking throughput; record discarded ids without touching accepted outputs.

## Authorization

Read-only progress inspection, ledger reads, and stale-worker checks may proceed without extra authorization. Starting or resuming workers, harvest appends, requeueing batches, and any production ledger mutation require explicit user authorization first.

## Narrow Probes

Prefer targeted read-only checks over broad recursive scans:

```bash
tail -n 120 <progress-ledger>
wc -l <verified_ids> <manifest.jsonl> <accepted_swe_ids_latest.txt> <accepted_swe_manifest_latest.jsonl>
find <production-root>/bundles -mindepth 1 -maxdepth 1 -type d | wc -l
```

For active batches, inspect event counts, worker pid/status, recent runner logs, and current verified ids before deciding whether to resume, requeue, or harvest.

## Reporting

Report the current production count, active batch labels, running/stale workers, newly accepted ids, discarded or failed ids, lock/ledger status, and exact report/log paths. If counts diverge, stop mutation and report the mismatch rather than trying to patch ledgers by hand.
