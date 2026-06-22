# Sigma2 Trace Correction — Full Derivation

## Problem

In SuSiE's variational Bayesian update for residual variance σ², the correct formula is:

```
σ² = (1/n) · [yᵀy − 2·yᵀX·E[b] + E[bᵀ·XᵀX·b]]
```

The term `E[bᵀ·XᵀX·b]` expands to:

```
E[bᵀ·XᵀX·b] = Σₗ wₗ · [ (B[l])ᵀ·XᵀX·B[l] + tr(XᵀX · Covₗ(b)) ]
```

where:
- `wₗ` = ELBO weight of effect l
- `B[l]` = posterior mean vector of effect l (p-vector)
- `Covₗ(b)` = posterior covariance matrix of effect l (p×p), which in SuSiE's factorized form is `diag(αₗⱼ·µ₂ₗⱼ − αₗⱼ²·µ₁ₗⱼ²)`

## The diagonal approximation (broken)

The **diagonal-only** version computes:

```
correction_diag = Σⱼ dⱼ · Σₗ wₗ · Varₗ(bⱼ)
                = Σⱼ dⱼ · Σₗ wₗ · (αₗⱼ·µ₂ₗⱼ − αₗⱼ²·µ₁ₗⱼ²)
```

where `dⱼ = (XᵀX)[j,j]` (diagonal elements only).

This is equivalent to the full trace `tr(XᵀX · Cov(b))` **only when** XᵀX is diagonal, because for a diagonal matrix D, `tr(D · C) = Σⱼ Dⱼⱼ · Cⱼⱼ` — off-diagonals of C don't matter since Dⱼₖ=0 for j≠k.

## When does diagonal-only fail?

1. **Synthetic normal data**: X ~ N(0,1) i.i.d. → XᵀX ≈ n·I (approximately diagonal). Diagonal approximation works perfectly. This is why the bug escaped initial testing.

2. **Real dosage data** (1000G, UKBB): SNPs are in LD blocks. XᵀX has large off-diagonal elements (|r| > 0.5 for correlated SNP pairs). The full trace `tr(XᵀX · Cov(b))` includes terms like `XᵀX[j,k] · Cov(b)[k,j]` for j≠k.

3. **Why the difference is always positive (sigma2 too high)**: In SuSiE, Cov(b) off-diagonals are negative when effects l have negative correlation between variants — common in fine-mapping where the model assigns probability mass to mutually exclusive causal variants. XᵀX off-diagonals are positive for positively-correlated SNPs (LD). So `XᵀX[j,k] · Cov(b)[k,j]` = (positive) × (negative) = negative contribution. The diagonal approximation misses these negative terms → **underestimates the correction** → σ² is too high → PIP accuracy degrades.

## The full trace fix

```
# Correct: compute full tr(XtX · Cov(b)) for each effect l
for l in range(L):
    # Cov_l = diag(α[l] * µ₂[l]) - diag(α[l]² * µ₁[l]²)
    # But we need the quadratic form, not element-by-element
    diag_part = torch.dot(d, alpha_l * mu2_l - alpha_l**2 * mu1_l**2)
    
    # Off-diagonal component: B[l]ᵀ·XtX·B[l] includes both diagonal
    # and off-diagonal products
    quad_part = B[l] @ (XtX @ B[l])
    
    correction += diag_part - quad_part
```

The full expression:
```
correction = Σⱼ dⱼ · Σₗ αₗⱼ·µ₂ₗⱼ 
           − Σₗ (B[l]ᵀ · XᵀX · B[l])
           + Σₗ (αₗⱼ²·µ₁ₗⱼ² handled separately)
```

## Detection pattern

| Test data | CPU σ² | GPU σ² (diag-only) | Verdict |
|-----------|--------|--------------------|---------|
| Synthetic N(0,1), 5K×10K | 1.020 | 1.020 | PASS (misleading) |
| 1000G chr22, 2504×2000 | 0.986 | 1.710 | FAIL (+73%) |

The diagnostic signature is: **all other metrics pass (ELBO, posterior means, PIP direction) but σ² is consistently too high ONLY on real correlated data**.

## Fix applied in susieR GPU v0.3

File: `src/susieR_gpu.py`, function `_update_sigma2`

Signature changed from:
```python
def _update_sigma2(X, ..., d, n):
```
to:
```python
def _update_sigma2(X, ..., XtX, n):
```

The call site in `susie_gpu()` passes the precomputed `XtX = X.T @ X` (computed once at init) instead of just the diagonal.

## General lesson for GPU ports

Any variational Bayes method with a linear-model term `E[bᵀ·XᵀX·b]` where X is a design matrix with correlated columns is vulnerable to this class of bug. The safe default: always compute the full quadratic form, never the diagonal approximation. The computational cost is `O(p²L)` but on GPU this is negligible for typical p < 10K. Only optimize to diagonal after proving on real correlated data that the approximation holds.
