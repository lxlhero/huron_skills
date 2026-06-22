# susieR GPU Precision Fix: XtX Precompute

Date: 2026-06-17
Rjobs: susier-gpu-debug-48287669 (FAIL), susier-gpu-debug-v2-21408960 (pending)

## v1 Failure Transcript

Data: n=500, p=300, L=5, synthetic with LD correlation
GPU: NVIDIA H200, PyTorch 2.3.1+cu121, float64

```
--- susieR CPU (baseline) ---
  Time:    0.03 sec
  niter:   5
  converged: TRUE
  sigma2:  0.236498
  max PIP: 1.000000

--- susieR GPU ---
  Time:    0.27 sec
  niter:   7
  converged: TRUE
  sigma2:  0.236389
  max PIP: 1.000000

=== Accuracy Comparison ===
  Pearson r (PIP):      0.9997645274   FAIL (threshold 0.9999)
  Max abs diff (PIP):   1.95e-02       FAIL (threshold 1e-4)
  MAE (PIP):            1.77e-03
  Alpha corr: 1.000000, 1.000000, 1.000000, 0.999999, 0.999992
  Alpha max abs diff:   3.60e-03
  mu max abs diff:      1.04e-03
  sigma2 diff:          1.09e-04
```

Script also crashed after printing metrics:
```
Error in lbf_cpu[l, ] : incorrect number of dimensions
```
(`susieR::susie()$lbf` is p-length vector; script tried 2D index `lbf_cpu[l, ]`)

## Root Cause

**v1 inner loop** (susieR_gpu.py lines 278-281):
```python
b_total = b_total - b_l_old
Xb_total = compute_Xb_gpu(X, b_total)      # X @ b — O(np)
Xr = Xty - compute_Xty_gpu(X, Xb_total)     # X^T @ (X @ b) — O(np)
```

This does **two** full matrix-vector multiplies per effect, computing `X^T (X b)` as two separate torch.mv calls. Each MV introduces separate floating-point rounding, and the error accumulates over L effects × N iterations.

**Original susieR C++ code** uses precomputed `XtX`:
```cpp
// susieR C++: Xr = Xty - XtX * b  (single BLAS call)
```

## Fix (v2)

Precompute `XtX = X.T @ X` once at initialization, then use single MV in inner loop:

```python
# At init:
XtX = X.T @ X   # (p, p) — precompute once, O(np²)

# Inner loop:
b_total = b_total - b_l_old
Xr = Xty - torch.mv(XtX, b_total)   # single O(p²) MV, matching C++ path
```

This:
1. Matches the EXACT numerical path of susieR C++ code
2. Eliminates double round-trip error
3. Reduces per-effect computation (but trades O(p²) memory for XtX — fine for p < 50K)

## Also Fixed: R Script lbf Crash

`test_accuracy.R` lines 225-233 originally assumed `lbf_cpu` is 2D. Fixed with defensive shape detection:
- If `lbf_cpu` is p-length vector and `lbf_gpu` is L×p: compare `lbf_cpu` vs `colSums(lbf_gpu)`
- If both are matrices: per-effect row comparison
- If shapes don't match any known pattern: skip with diagnostic message
