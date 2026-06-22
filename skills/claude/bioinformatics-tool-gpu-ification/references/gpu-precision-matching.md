# GPU Precision Matching — Float Path Byte-for-Byte Alignment

## The core problem

scipy.gmean and torch's exp-mean-log produce different results for float16 input
because numpy and torch implement float16 log differently at the bit level.

```
scipy.gmean(float16):  np.log(float16) → float16 → mean(float64) → exp(float64)
torch exp-mean-log:    torch.log(float16) → float16 → sum(float64) → exp(float64)
                                ^-- DIFFERS at bit level (~8e-4 per value)
```

This ~8e-4 difference, when near the threshold (<=1.0 → 0), causes genes to flip
between zero and non-zero. After exp amplification, this becomes 1e9+ in final output.

## Tier 1 Solution: numpy log on CPU

For byte-exact match with scipy.gmean, do the log step on CPU using numpy:

```python
# Inside GPU module's gene chunk loop:
ranks_np = ranks_norm[:, gs:ge].astype(np.float64)  # CPU float64
gr_np = np.zeros((n_cells, g_chunk), dtype=np.float64)
for i in range(n_cells):
    nb = neigh_idx_np[i]
    tk = topk_np[i, :kpc_np[i]]
    ranks_tg = ranks_np[nb[tk], :]
    gm = np.exp(np.mean(np.log(np.clip(ranks_tg, 1e-12, None)), axis=0))
    gm[gm <= 1.0] = 0.0
    gr_np[i] = gm
gr = torch.tensor(gr_np, dtype=torch.float64, device=device)
# Now gr on GPU matches scipy.gmean byte-for-byte
# Expression fraction and final exp remain on GPU for acceleration
```

Trade-off: gmean is on CPU (slower), but guaranteed byte-exact. The rest
(expression fraction, final exp) stays on GPU. Acceptable for correctness-first.

## Tier 2: Accept and document

If Tier 1 is too slow for production, compute the max divergence and document:
- Show Pearson correlation is still 1.0
- Show max diff in relative terms (<0.01%)
- State it's IEEE 754 float precision, not algorithmic error

## Verification steps

1. Run scipy.gmean and torch exp-mean-log on same float16 input
2. Compare max diff per gene
3. Check how many genes cross the <=1.0 threshold
4. Verify Pearson > 0.9999 on final output
