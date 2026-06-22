# Standardize Mismatch Bug: Diagnosis & Fix

## Symptoms (susieR v0.3–v0.4, medium scale 2504×2000_L5)

| Metric | 500×500 (PASS) | 2504×1054 (FAIL) | 2504×2115 (NEAR PASS) |
|--------|----------------|------------------|----------------------|
| sigma2 ratio | 1.0043 | 1.000255 ✓ | 1.000502 ✓ |
| PIP r | 1.000000 | 0.995641 ✗ | 0.999991 ✓ |
| max_diff | 5.91e-05 | 0.177647 ✗ | 0.00282 ~ |
| alpha cor | 0.999998 | 0.906763 ✗ | 1.000000 |
| mu cor | 1.000000 | 0.995277 | 0.999976 |
| mu2 cor | 1.000000 | 0.999295 | 0.999976 |

Key diagnostic signal: sigma2 is PERFECT (ratio ~1.0), mu2 is excellent (>0.999), but alpha diverges (~0.90). The divergence amplifies through softmax: lbf → alpha → PIP.

## Root Cause

`susieR::susie()` defaults to `standardize=TRUE` — it internally mean-centers and unit-variances each column of X before the IBSS algorithm. The GPU kernel (`susieR_gpu.py`) does NOT standardize (assumes pre-standardized input from the wrapper).

In the wrapper code (`susieR_gpu_wrapper.R`):
- CPU path: `susieR::susie(X=X, y=y, L=L, ...)` — standardize=TRUE by default
- GPU path: calls `py$susieR_gpu$susie_gpu_numpy(X_np=X, ...)` — no standardization

Result: CPU runs on standardized X, GPU runs on raw X. Different inputs → different posteriors.

The 500×500 benchmark data happened to be already ~standardized (generated from random subset), so no difference. The 2504×2115 data also apparently close. But the 2504×1054 data was NOT standardized → big PIP divergence.

## Fix (v0.5)

In `susieR_gpu_wrapper.R`, CPU path:

```r
return(susieR::susie(
  X = X, y = y, L = L,
  standardize = FALSE,   # match GPU path
  ...
))
```

Also in `susie_gpu_validate()` (direct susieR::susie call):

```r
fit_cpu <- susieR::susie(X = X, y = y, L = L, standardize = FALSE, ...)
```

## Diagnostic Methodology

When GPU post-bug (sigma2 fix confirmed) still shows PIP divergence:

1. Run fixed-seed comparison (set.seed(42) before both CPU and GPU) to rule out stochastic effects
2. Print per-component correlations: alpha, mu, mu2
3. The divergence pattern tells you where the bug lives:
   - mu2 bad but sigma2 good → posterior variance computation bug
   - mu good but alpha bad → softmax amplification of lbf errors
   - ALL diverging → input data mismatch (standardize, scaling, NA handling)

## Lesson

When wrapping an R function with a GPU replacement, audit ALL default parameters of the original function. Any that silently transform input data (standardize, scale, center, intercept, na.action) are potential divergence sources. The bug is invisible on standardized test data.
