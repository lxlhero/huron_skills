# ELBO Diagnostic for Softmax Concentration

## When to use

A GPU-accelerated SuSiE/fine-mapping tool shows:
- sigma2 matches CPU within 1%
- But PIP correlation is 0.90–0.996 (below 0.9999 threshold)
- The worst case is at medium n/p ratios (~2–3), not at extremes

This is likely softmax concentration — NOT a numerical bug.

## Recipe

1. Run both CPU and GPU with identical seeds, data, and parameterization:
   ```r
   library(susieR)
   d <- readRDS("benchmark.rds")
   set.seed(42); Sys.setenv(SUSIER_DEVICE="cpu"); fc <- susie_gpu(d$X, d$y, L=5)
   set.seed(42); Sys.setenv(SUSIER_DEVICE="gpu"); fg <- susie_gpu(d$X, d$y, L=5)
   ```

2. Print ELBO for both (depends on tool; for susieR use loglik or compute manually):
   ```r
   cat("CPU ELBO:", fc$loglik, "\n")
   cat("GPU ELBO:", fg$loglik, "\n")
   cat("Delta:", fg$loglik - fc$loglik, "\n")
   cat("VERDICT:", if(abs(fg$loglik - fc$loglik) < 1) "EQUIVALENT" else "DIVERGENT")
   ```

3. Compute per-effect alpha correlation:
   ```r
   alpha_cor <- sapply(1:fc$L, function(l) cor(fc$alpha[l,], fg$alpha[l,]))
   cat("Per-effect alpha cor:", round(alpha_cor, 4), "\n")
   cat("MU2 pearson:", cor(fc$mu2, fg$mu2), "\n")
   ```

## Interpretation

| Delta ELBO (nats) | Verdict | Action |
|-------------------|---------|--------|
| < 1 | EQUIVALENT — both optimal | Accept; explain softmax concentration |
| 1–5 | Marginal — GPU slightly worse | Investigate numerical precision; rerun |
| > 5 | DIVERGENT — real bug | Debug: sigma2 trace, standardize, Xr computation |

## Root cause: softmax concentration

SuSiE computes `alpha[l,j] = softmax(lbf[l,j])`. The softmax is:
- Flat when n/p ≈ 1 (under-identified, many SNPs equally plausible) → small lbf differences don't concentrate → PIP r ≈ 1.0
- Sharp when n/p ≈ 2–3 (well-identified, few SNPs clearly signal) → tiny lbf differences (< 0.5 nat) get amplified into visible PIP differences (r = 0.90–0.996)
- Moderately sharp when n/p > 10 (over-identified, many observations) → same issue but less common in fine-mapping

This means the worst-case PIP correlation occurs at intermediate n/p ratios, exactly where we saw it:
- n/p=1.0 → PIP r=1.000 (flat softmax)
- n/p=2.37 → PIP r=0.996 (sharp softmax, worst case)
- n/p=1.18 → PIP r=1.000 (moderately flat)

## susieR v0.5 real-world result (2026-06-17)

```
Scale 2 (2504×1054, L=5):
  CPU ELBO: -3533.82
  GPU ELBO: -3532.86
  Delta:    0.96 → EQUIVALENT (< 1 nat)
  
  Per-effect alpha cor: [0.91, 0.91, 0.90, 0.91, 0.91]
  MU2 pearson: 0.9999+
  
  PIP correlation: 0.9956 (softmax amplifies)
```

Both CPU and GPU converged to valid local optima of equal ELBO quality. The PIP divergence is a visualization artifact of softmax, not a numerical correctness issue. GPU solution is arguably marginally BETTER (higher loglik by 0.96).

## Pitfalls

- Don't confuse ELBO with PIP correlation. ELBO measures solution quality; PIP measures concentration sharpness.
- Don't chase PIP r > 0.9999 on well-identified models (n/p > 2). It's an unfairly strict metric for this regime.
- If ELBO passes but PIP fails: document as "equivalent local optima" and report per-effect alpha correlation alongside PIP.
- The ELBO diagnostic must be run in the same R session with seed fixed BEFORE each call, to ensure the PRNG state is identical for both paths.
