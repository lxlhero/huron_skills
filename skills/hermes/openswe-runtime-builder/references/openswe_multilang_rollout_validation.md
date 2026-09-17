# OpenSWE Multi-Language Rollout Validation

Use this reference when independently accepting, auditing, or rollout-testing a mounted Go/C/C++ delivery, or when writing a prompt for a dedicated validation agent. Read `openswe_multilang_delivery.md` first for the production and bundle contracts.

## Validator Role

The rollout validator is read-only and independent:

- Do not repair, regenerate, mutate, promote, or re-harvest SWE while validating them.
- Write reports, extracted worktrees, logs, and run results to a fresh sibling directory outside the delivery root.
- Treat existing summaries and audit JSON as claims to cross-check, not proof to reuse.
- Do not persist credentials and do not run destructive Docker cleanup.
- Run actual red/green containers with networking disabled. If upstream semantic evidence requires network access, record that separately; it does not change the offline runtime contract.

## Gate Order

### 1. Inventory and integrity

Check 100% of the delivery before runtime work:

- Count `bundles/golang/<id>`, `bundles/c/<id>`, and `bundles/c++/<id>` and reject `cpp` aliases in the public tree.
- Compare ID sets, not only counts, across bundle directories, `ids.txt`, accepted-ID ledgers, manifests, and `dataset.jsonl`. Require exactly one canonical language assignment per ID.
- Verify required bundle files, source archive readability, safe archive paths, no escaping symlinks, and declared base-revision identity.
- Verify the image archive checksum, load it through the shipped loader, and record image ID plus toolchain versions.
- Verify declared critical-file checksums. If dependency caches are intentionally excluded, make that scope explicit instead of claiming full-tree coverage.
- Scan user-visible metadata, scripts, runners, and patches for producer paths or undeclared external dependencies. Do not mechanically flag a denylist regex literal inside the validator itself; classify findings by file semantics.
- Reject process artifacts in the clean product root, including run results, compiler output, worktrees, repair queues, temporary files, and logs.

### 2. Verifier-quality/static-oracle audit

Inspect every `test_patch.diff`, eval script, direct runner, and relevant metadata. Red/green is not sufficient when the verifier recognizes the answer rather than the behavior.

Reject or quarantine tests that:

- read implementation source and assert exact strings, regexes, AST shapes, symbol placement, or snippets introduced by the gold patch;
- read or reconstruct `gold_patch.diff`, expected additions, or expected removals;
- use source markers, comments, function names, or gold-only text as the primary discriminator;
- skip the intended build/test execution and merely inspect repository contents.

High-recall signals include `gold_patch_static_discriminator`, `source_marker_oracle`, `static source-content oracle`, `dependency-light source-content oracle`, `oracle_static_`, `oracle_source_check_`, `ORACLE_STATIC_FAIL`, `openswe_oracle_test.py`, `expected_added`, and `missing marker`. A keyword hit requires semantic classification, but an explicit source/gold oracle is a hard rejection even if runtime red/green passes.

### 3. Independent patch preflight

For each bundle, create separate clean writable snapshots:

1. Restore and identity-check the declared base.
2. Apply only `test_patch.diff` to the test-only snapshot.
3. Apply `test_patch.diff` and then `gold_patch.diff` to another clean snapshot.
4. Reject patch conflicts, reversed/already-applied patches, silent no-ops, wrong repository identity, and invalid test paths.

Do not interpret a shared patch, build, dependency, collection, or environment failure as a valid red result.

### 4. Image/toolchain smoke

The shared multi-language image must preserve the Python base while adding native toolchains. Record and minimally execute Python, conda, Go, gcc, g++, CMake, Make, and Git. If a required tool is absent, reject every SWE that needs it rather than allowing their failures to count as red.

### 5. Three-language smoke, then full strict red/green

Run one C, one C++, and one Go bundle before the full batch. Invoke each direct runner by absolute bundle path from an unrelated current directory.

For every accepted ID:

```text
testonly: OPENSWE_EXIT_CODE is present and nonzero
gold:     OPENSWE_EXIT_CODE is present and equals 0
```

Missing markers, timeouts, swallowed command failures, or reliance on container/shell exit status are failures. Inspect both logs: the same environment or patch failure on both sides is not a behavioral red/green result.

Use the path-aware validator shipped with the delivery when the public layout is `bundles/<language>/<id>`. Do not blindly use an older verifier that assumes `bundles/<id>` or `<language>/bundles/<id>`. A typical command is:

```bash
cd /path/to/multilang_delivery
./scripts/load_base_image.sh
python3 scripts/validate_delivery.py \
  --delivery-root . \
  --report /path/outside-delivery/delivery_gate.json \
  --results-dir /path/outside-delivery/results \
  --workers 4 \
  --timeout-seconds 1800 \
  --run-redgreen \
  --strict
```

### 6. Semantic review

Review every machine-suspicious or rejected item and at least 5% of machine-passing items, rounded up. Cover every delivered language and, where practical, each major repository/build-system cluster.

For each sample, bind the problem statement, same-instance trajectory or upstream PR evidence, test behavior, and gold behavior. Confirm that the test reproduces the stated issue and that the gold patch fixes that behavior without the test depending on gold source shape.

### 7. Relocation/user simulation

Copy or move at least one C, one C++, and one Go bundle to fresh unrelated paths. Run them using only the copied bundle, Docker, and the declared shared image. Mount the bundle read-only and a fresh work directory writable. Reject dependencies on the producer repository, raw JSONL, repair directories, sibling bundles, or historical process artifacts.

## Reject Conditions

Overall acceptance is blocked by any unresolved:

- count, ID-set, language, manifest, or checksum mismatch;
- missing/unsafe bundle input or undeclared external path;
- image identity/toolchain mismatch;
- patch preflight failure;
- static/gold-source oracle;
- test-only zero/missing marker, gold nonzero/missing marker, or timeout;
- shared infrastructure failure misclassified as behavior-red;
- arbitrary-working-directory or relocation failure;
- validation writes inside the clean delivery root.

Quarantine failing IDs with precise reasons. Do not repair them inside the validator role and then count them as independently accepted.

## Required Report

Report an overall `ACCEPT` or `REJECT`, plus:

- delivery root and fresh report root;
- total and per-language counts;
- bundle/ledger ID-set comparison;
- checksum, image ID, and toolchain evidence;
- static-oracle findings;
- patch-preflight results;
- smoke and full per-language red/green totals;
- semantic samples and evidence basis;
- relocation results;
- per-ID failure/suspicious queues with exact reasons;
- commands executed and absolute paths to structured reports and logs;
- separate classifications for delivery defects, validator defects, and host/Docker infrastructure defects.

Never declare success solely from a previous audit, aggregate process exit code, or a nominal 100% red/green count without the static-oracle and portability gates.
