# Real-Data Benchmark Workflow

How to run GPU benchmark on official/production data (not just simulated data).

## When simulated data is not enough

Simulated data proves computational correctness and speedup. Real data proves scientific validity.
Use this workflow when the output needs reviewer/leader-level credibility.

## Generic workflow

1. Download official tutorial/benchmark data for the tool
2. Transfer data to shared storage (extract on Pod to avoid root squash)
3. Run the upstream pipeline steps to generate intermediate data (use CPU or GPU as the tool dictates)
4. Run hotspot step with original CPU code → save reference output
5. Run hotspot step with GPU code on same input → save GPU output
6. Compare reference vs GPU output (Pearson correlation, max diff, R²)

## gsMap specific

### Data
- Tutorial data: yanglab.westlake.edu.cn/data/gsMap/ (651MB resource + 2.37GB example)
- Example: E16.5_E1S1.MOSTA mouse embryo spatial transcriptomics (h5ad + GWAS)

### Pipeline and hotspot
- Step 1: `gsmap run_find_latent_representations` (GNN training, GPU → writes latent_GVAE to h5ad)
- Step 2: `gsmap run_latent_to_gene` (CPU, hotspot: per-cell loop computing marker scores)
- GPU version: replaces `compute_regional_mkscore` loop with vectorized CUDA operations

### Benchmark script pattern
```python
# Both CPU and GPU versions accept the same LatentToGeneConfig
# Just call different modules on copies of the same h5ad
from gsMap.latent_to_gene import run_latent_to_gene as run_cpu
from gsMap.latent_to_gene_gpu import run_latent_to_gene as run_gpu

run_cpu(config_cpu)   # saves .feather to CPU workdir
run_gpu(config_gpu)   # saves .feather to GPU workdir
compare_feather_files(cpu_path, gpu_path)
```

### Output comparison
Both produce `.feather` files (marker score matrix: genes × spots).
Comparison: Pearson correlation, R², max/mean/median abs diff, per-gene correlation, exact match rate.
Float16 precision → expect Pearson > 0.9999, max diff < 1e-4.

### Key pitfalls
- Don't run CPU and GPU on the same workdir (file conflicts). Copy h5ad to separate dirs.
- GPU warmup before timing: `torch.cuda.synchronize()` + dummy tensor allocation.
- The `.feather` file is the canonical output — compare that, not intermediate numpy arrays.
