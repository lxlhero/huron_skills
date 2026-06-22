# susieR Benchmark Data Generation (1000G chr22)

Validated workflow for producing three-scale benchmark .rds from real 1000 Genomes.

## Data Source

1000G Phase 3 chr22: `ALL.chr22.phase3_shapeit2_mvncall_integrated_v5b.20130502.genotypes.vcf.gz`
- 196MB compressed, ~1.1M variants, 2,504 samples
- Download: `curl -L -o chr22.vcf.gz "https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/..."`

## Pipeline

1. Mac downloads VCF → SCP to GPFS (via execute_code subprocess, not terminal background)
2. `rjob submit --gpu 0 --image <l1-base>` runs `prepare_benchmark.R` with GPFS mount wait loop
3. Outputs .rds directly to GPFS `data/`

## Output (validated 2026-06-17)

| File | n | p | Notes |
|------|---|---|-------|
| bench_500x500_L3.rds | 500 | 500 | Subsampled |
| bench_2504x2000_L5.rds | 2504 | 2000 | Full samples |
| bench_2504x5000_L10.rds | 2504 | 2115 | Truncated by MAF≥1% |

RDS fields: $X (float64, standardized), $y, $true_coef, $causal_idx, $snr, $source="1000G_Phase3_chr22"

## Key Limitation

APOE region yields only ~2115 variants after QC. Script handles gracefully. For larger p: merge multiple regions.
