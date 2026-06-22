# GPU Chunked Processing for Large Spatial Transcriptomics Data

## Problem

When vectorizing per-cell loops on GPU, the naive approach of expanding neighbor
tensors creates massive intermediate allocations:

```
ranks_t:       (N, G)          float32  121767 × 28204 × 4 = 13.7 GB   ✓ fits
neigh_ranks:   (N, K, G)       float32  121767 × 201 × 28204 × 4 = 2.7 TB  ✗ OOM
```

K = num_neighbour_spatial (201), G = genes (28K), N = cells (121K).

The expansion `ranks_t[neigh_t]` creates a (N, K, G) view via advanced indexing,
which materializes as a full dense tensor on GPU.

## Solution: Gene Chunking

Process genes in chunks that fit within a ~5 GB VRAM budget per chunk:

```python
chunk_size = max(50, min(500, int(5e9 / (n_cells * K * 4))))
# For 121K cells × 201 neighbors: ~51 genes per chunk

for g_start in range(0, n_genes, chunk_size):
    g_end = min(g_start + chunk_size, n_genes)
    ranks_chunk = ranks_norm[:, g_start:g_end]  # to GPU
    neigh_ranks = ranks_chunk[neigh_t]           # (N, K, chunk) ~5 GB
    top_ranks = neigh_ranks[batch_idx, topk]     # (N, k_select, chunk)
    # ... compute gmean, expression fraction ...
    mk_score[:, g_start:g_end] = result.cpu().numpy()
    del ranks_chunk, neigh_ranks, top_ranks  # free VRAM
```

## VRAM Budget Formula

```
chunk_vram = n_cells × K × chunk_size × 4 bytes  (float32)
chunk_vram += n_cells × K × chunk_size × 4        (if expression fraction)
Total ≈ n_cells × K × chunk_size × 8 bytes
```

For H200 (150 GB), target 5 GB per chunk → 553 chunks for 28K genes.

## When to Use

- N > 50K cells AND G > 10K genes → almost certainly need chunking
- N < 20K cells → full vectorization likely fits
- Always add the chunking fallback in production GPU code — costs nothing when
  data fits, prevents OOM when it doesn't.

## Implementation Pattern (Monkey-Patch)

When you can't modify the installed package (e.g., no sudo on Pod), monkey-patch
the function before use:

```python
import gsMap.latent_to_gene_gpu as gpu_mod
gpu_mod.compute_marker_scores_gpu = compute_marker_scores_gpu_chunked
```

The `run_latent_to_gene` wrapper calls `compute_marker_scores_gpu` by name, so
replacing the function object at module level is sufficient — no need to modify
the caller.
