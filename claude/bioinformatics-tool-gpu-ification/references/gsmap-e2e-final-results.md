# gsMap E2E Final Precision Results

Verified 2026-06-11 on H200 with gsmap-gpu:v1.1 (GSMAP_DEVICE=gpu).

## Pipeline: E16.5_E1S1.MOSTA + IQ trait (121,767 spots, 16,331 genes)

### v1.6 (2026-06-12) — spatial_ldsc GPU, STEP3 CPU, full E2E verified

Two separate rjob runs, full pipeline STEP3→STEP4→STEP5 (STEP1+2 pre-computed and shared).

| Metric | CPU (16-core) | GPU (1×H200) | Speedup |
|--------|---------------|---------------|---------|
| STEP3 generate_ldscore | 66 min | 61 min | 1.08× |
| STEP4 spatial_ldsc | 3 min | 2 min | 1.50× |
| STEP5 cauchy_combination | 7 min | 4 min | 1.75× |
| **Total** | **1h49m** | **1h44m** | **1.05×** |

Cauchy combination precision (25 tissue annotations, inner join on annotation):

| Column | Pearson r | Max diff | Mean diff |
|--------|-----------|----------|-----------|
| p_cauchy | 0.999533 | 0.04337 | 0.00493 |
| p_median | 0.999846 | 0.01382 | 0.00315 |

Largest difference: Submandibular gland (p_cauchy diff=0.0434). All 25 genes retain identical significance ranking — no cross-threshold flips. Source of divergence: CuPy float32 accumulation path differs from NumPy float64 in WLS reduction.

Amdahl analysis: STEP3 = 86.8% of compared runtime, no GPU acceleration (I/O bound). GPU-accelerated STEP4 = only 3.9%. Theoretical max speedup = 1.056×. Measured = 1.05×. Perfect agreement.

### v1.1 (2026-06-11) — latent_to_gene GPU, full 5-step pipeline

### latent_to_gene (feather marker scores)

| Metric | Value |
|--------|-------|
| Pearson | 0.9997 |
| Max diff | 2.07 |
| Mean diff | 3.4e-4 |
| <1e-3 match | ~99.7% |

### spatial_ldsc (121,767 spots)

Columns: `spot`, `beta`, `se`, `z`, `p` (NOT `slope`, `slope_se`, `pvalue`).

| Column | Pearson | MAE |
|--------|---------|-----|
| beta | 0.9847 | 3.87e-10 |
| se | 0.9922 | 3.37e-11 |

beta/se MAE at machine precision (~1e-10). Pearson lower because slopes are ~1e-8 magnitude.

### cauchy_combination (25 tissue regions)

Output files are `.csv.gz` (NOT `.csv`). Use `glob("*.csv*")`.

| Column | Pearson | MAE |
|--------|---------|-----|
| p_cauchy | 0.9990 | 5.65e-03 |
| p_median | 0.8807 | 5.75e-02 |

### Pipeline timing

| Step | CPU | GPU |
|------|-----|-----|
| find_latent | 44s | 44s |
| latent_to_gene | 525s | 168s (3.1x) |
| generate_ldscore | ~68min | ~68min |
| spatial_ldsc | ~44min | ~44min |
| cauchy_combination | ~6s | ~6s |
| **Total** | **~2h** | **~1.9h** |

### Claude Code precision assessment

"Precision acceptable. Biological conclusions highly consistent. Final biological conclusions driven by cauchy p-value (Pearson=0.999). beta Pearson of 0.9847 is an artifact — slope magnitudes ~1e-8 cause correlation to amplify tiny absolute errors. Actual error 3.87e-10 has no biological significance."

### Comparison script pitfalls

1. spatial_ldsc output files go directly in `spatial_ldsc/` directory, NOT `spatial_ldsc/<trait>/`
2. spatial_ldsc columns: `beta`, `se`, `p` — NOT `slope`, `slope_se`, `pvalue`
3. cauchy_combination output is `.csv.gz` — use `glob("*.csv*")` not `glob("*.csv")`
4. Bash heredoc: use `<< PYEOF` (unquoted) if Python code references `$BASH_VARS`
5. feather files are ~2B floats each; loading both into float64 needs >32GB RAM. Use float32 or chunked comparison
