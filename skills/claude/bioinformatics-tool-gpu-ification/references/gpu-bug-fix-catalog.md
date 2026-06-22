# GPU Bug Fix Catalog — gsMap v1.0 → v2.1

## Bug 1: Neighbor padding with self (CRITICAL)
- **Symptom**: GPU output completely different from CPU (Pearson 0.00027, max diff 4e9)
- **Root cause**: When a cell has fewer than K spatial neighbors, padding uses cell index `i` (self). Cosine similarity with self = 1.0, topk selects padding entries as "best neighbors"
- **Fix**: Use valid_mask + set padding similarity to `-inf`. `torch.where(valid_t, sims, float('-inf'))`
- **Detection**: Single-cell neighbor comparison → mismatch found

## Bug 2: frac_region clamp(0,1) (CRITICAL)
- **Symptom**: All marker scores are wrong after expression fraction step
- **Root cause**: `torch.clamp(frac_region, 0.0, 1.0)` compresses all values ≤1.0, then `frac_region[frac_region <= 1.0] = 0.0` zeros everything
- **Fix**: Remove clamp, keep only threshold `frac_region[frac_region <= 1.0] = 0.0`
- **Detection**: Step-by-step value trace → frac_region always 0

## Bug 3: Fixed topk size (MEDIUM)
- **Symptom**: Cells with <k_select neighbors get wrong results
- **Root cause**: `torch.topk(sims, k_select)` picks k_select entries even when fewer valid neighbors exist
- **Fix**: Dynamic per-cell k = min(k_select, valid_neighbor_count), mask invalid entries in gmean and frac computation
- **Detection**: Checked valid_neighbor_counts per cell

## Bug 4: Float precision mismatch (MEDIUM)
- **Symptom**: 3-4 genes per cell flip threshold (≤1→0) causing 4e9 errors after exp amplification
- **Root cause**: gsMap passes float16 to scipy.gmean which does `np.log(f16)→f16, np.mean→f64, np.exp→f64`. GPU used float32 log which gives different results for values near 1.0
- **Fix**: Tier 2 — full float64 gmean path. Then v2.1 — Tier 1: numpy log on CPU for byte-exact scipy.gmean match
- **Detection**: scipy.gmean vs torch float16 log comparison → ~8e-4 diff per gene

## Bug 5: k_tensor double-unsqueeze (MINOR, build-time)
- **Symptom**: Shape mismatch (N, N, G) instead of (N, G) in gmean division
- **Root cause**: `k_tensor` already has shape (N, 1) from `.unsqueeze(1)`. Another `.unsqueeze(1)` makes it (N, 1, 1), causing wrong broadcast
- **Fix**: Remove extra `.unsqueeze(1)` from `k_tensor.clamp(min=1).float()`
- **Detection**: Shape error in benchmark_v2.py

## Bug 6: rn = ranks / (gM + 1e-12) precision promotion (build-time)
- **Symptom**: Inexplicable diff between identical-looking CPU and GPU code
- **Root cause**: `1e-12` is Python float (float64), promotes entire expression to float64. Original gsMap uses `ranks /= gM` (float16 in-place)
- **Fix**: `rn = ranks / gM` followed by `rn[~np.isfinite(rn)] = 0`
- **Detection**: Dtype tracing — rn was float64, expected float16

## Bug 7: topk_mask_3d missing after gmean refactor (v2.1 regression)
- **Symptom**: NameError on `topk_mask_3d` after moving gmean to numpy
- **Root cause**: gmean block originally defined `topk_mask_3d`. When gmean moved to numpy, the definition was deleted but expression fraction still referenced it
- **Fix**: Add `topk_mask_3d = topk_mask_2d.unsqueeze(2).expand(n_cells, max_k, g_chunk)` as standalone line before expression fraction block
- **Lesson**: When refactoring a code block, grep for all downstream references to variables defined inside it

## Bug 8: Full-scale OOM with adata_chunk[neigh_t] (v2.1)
- **Symptom**: CUDA OOM allocating 91 GB on full 121K×28K data
- **Root cause**: VRAM calculation used `max_k` (51) but `adata_chunk[neigh_t]` uses `K` (201). With 500 genes/chunk: 121K × 201 × 500 × 8 = 97 GB
- **Fix**: Use `K` (not `max_k`) in VRAM calculation: `bytes_per_gene = n_cells * K * 8`. Reduce chunk to ~75 genes for safety
- **Detection**: Traced which tensor allocation triggered the OOM

## Key lesson
ALL bugs were found by systematically isolating each computation step: neighbors → gmean → threshold → frac_region → final exp. Single-cell trace with `np.allclose` between CPU and GPU intermediate values is the fastest detection method. When refactoring, grep for downstream variable references.
