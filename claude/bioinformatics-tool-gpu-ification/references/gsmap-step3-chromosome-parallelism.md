# gsMap STEP3 LD Score Generation: Chromosome-Level Parallelism

## Problem

STEP3 (`generate_ldscore`) is the dominant bottleneck in gsMap — **62% of total E2E runtime (66 minutes)**. The step processes 22 chromosomes **serially** in a `for chrom in range(1, 23)` loop, despite each chromosome being completely independent (separate input PLINK files, separate output files, no cross-chromosome data dependencies).

### STEP3 time breakdown (66 min total)

| Sub-phase | Time | % of STEP3 | GPU status |
|-----------|------|------------|------------|
| Phase A: LD correlation matrix (torch.mm) | ~53 min | 80% | Already GPU |
| Phase B: sparse×dense regression + weight calc | ~10 min | 15% | CPU only |
| I/O: PLINK reads + feather writes | ~3 min | 5% | — |

## Key Discovery: `--chrom N` already exists

The `generate_ldscore.py` CLI already supports single-chromosome mode:

```
gsmap run_generate_ldscore --chrom 1 --bfile_root ...
gsmap run_generate_ldscore --chrom 2 --bfile_root ...
```

Each invocation processes exactly one chromosome. This means **no Python code changes are needed** to enable parallelism — the building blocks are already there.

## The Only Blocker: `.done` Sentinel File

All per-chromosome file outputs are independently named (verified by code audit):

```
baseline/baseline.{chrom}.l2.ldscore.feather
baseline/baseline.{chrom}.l2.M
baseline/baseline.{chrom}.l2.M_5_50
{sample_name}_chunk{N}/{sample_name}.{chrom}.l2.ldscore.feather
snp_gene_weight_matrix/{chrom}.snp_gene_weight_matrix.feather
w_ld/weights.{chrom}.l2.ldscore.gz
SNP_gene_pair/SNP_gene_pair_chr{chrom}.feather
```

**Zero cross-chromosome write conflicts.**

The single blocker is `run_generate_ldscore()` unconditionally touching the `.done` file at its end (line 1015-1016 in `generate_ldscore.py`). When 22 parallel `--chrom N` processes run, the first one to finish touches `.done`, and downstream `spatial_ldsc` (which checks for `.done` in `run_all_mode.py` line 129-132) incorrectly assumes all 22 chromosomes are complete.

### Fix (one line conceptual change)

Make `--chrom N` mode skip the `.done` touch. The parallel wrapper touches `.done` only after ALL 22 subprocesses succeed.

## Parallelization Approaches (Ranked)

| Approach | Code changes | Risk | Workload |
|----------|-------------|------|----------|
| **Shell `xargs -P`** | Zero Python changes | Very low | 0.5 day |
| Python `multiprocessing` (spawn) | Refactor `run_generate_ldscore` | Medium-high (CUDA spawn compat) | 2-3 days |
| CUDA Stream/MPS | Infeasible | — | — |
| Ray/Dask distributed | New dependencies | High | 4-5 days |

### Recommended: Shell-level parallel (xargs -P)

```bash
# Run 4 chromosomes in parallel (tune based on available CPU cores)
seq 1 22 | xargs -P 4 -I {} \
  gsmap run_generate_ldscore --chrom {} --bfile_root ... --workdir ...

# After all succeed, touch the done file
touch {workdir}/{sample_name}/generate_ldscore/{sample_name}_generate_ldscore.done
```

GPU strategy: Since STEP3 compute density is low (torch.mm ~0.176 TFLOPs, bottleneck is PLINK I/O), run with `CUDA_VISIBLE_DEVICES=""` to force CPU path. This avoids GPU memory pressure (single-chromosome `annot` matrix ~32GB float32), allowing more parallel workers.

## Expected Speedup

| Parallelism | STEP3 time | Speedup |
|-------------|-----------|---------|
| Serial (current) | 66 min | 1× |
| 4-way parallel | ~17 min | ~3.9× |
| 8-way parallel | ~9 min | ~7.3× |
| 22-way (theoretical max) | ~5 min | ~13× |

Limiting factor: chr1 has ~200K SNPs (largest), chr22 has ~30K SNPs (smallest). LD computation scales as O(n_snps²), so chr1 dominates. Practical cap is ~5-6×.

## Lessons for General Bioinfo GPU-ification

1. **Check for `--chrom N`/single-unit mode before building parallelism.** Many bioinfo tools already have per-chromosome or per-sample CLI flags — they were designed for debugging but double as parallelism primitives.

2. **Sentinel files break parallelism.** `.done` markers, lock files, and checkpoint sentinels are almost always designed for serial execution. Parallelizing requires making them aware of partial completion (e.g., individual `.done.{chrom}` files or counting completed outputs).

3. **Shell-level parallelism beats code rewrites for embarrassingly parallel problems.** When tasks have zero shared state and independent I/O, `xargs -P` or GNU `parallel` are safer than `multiprocessing` (no fork/spawn issues, no CUDA context conflicts, transparent logging).
