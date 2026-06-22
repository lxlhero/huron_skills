#!/usr/bin/env python3
"""
Template: GPU Benchmark on Real Data (Skip Training)
=====================================================
Pattern for benchmarking GPU-accelerated bioinformatics tools.
Key design decisions:
  - Separate h5ad copies for CPU and GPU (avoid in-place modification conflicts)
  - Inject synthetic latent representations instead of running training (pure inference)
  - GPU processing chunked by genes to avoid OOM on large datasets
  - Monkey-patch pattern when system module can't be edited directly

Adapt for your tool by replacing:
  - run_cpu / run_gpu imports
  - LatentToGeneConfig → your tool's config class
  - build_config() → your tool's config builder
  - compare_mkscores() → your output comparison logic
"""

import sys, time, json, argparse, numpy as np
from pathlib import Path
import torch, scanpy as sc

# --- Replace with your tool's imports ---
# from your_tool.cpu_module import run as run_cpu
# from your_tool.gpu_module import run as run_gpu


def inject_synthetic_latent(adata, latent_dim=32, seed=42):
    """Generate realistic latent representations via PCA of expression data."""
    from sklearn.decomposition import PCA
    rng = np.random.default_rng(seed)
    n_cells = adata.n_obs
    
    X = adata.X.toarray() if hasattr(adata.X, 'toarray') else adata.X
    X_log = np.log1p(X.astype(np.float64))
    
    pca = PCA(n_components=min(latent_dim, n_cells, X_log.shape[1]), random_state=seed)
    latent = pca.fit_transform(X_log)
    
    if latent.shape[1] < latent_dim:
        noise = rng.normal(0, 0.1, (n_cells, latent_dim - latent.shape[1]))
        latent = np.hstack([latent, noise])
    else:
        latent = latent[:, :latent_dim]
    
    latent += rng.normal(0, 0.05, latent.shape)
    adata.obsm['latent_GVAE'] = latent.astype(np.float32)
    return adata


def compare_outputs(cpu_path, gpu_path):
    """Compare CPU and GPU output files. Adapt to your tool's output format."""
    import pandas as pd
    
    df_cpu = pd.read_feather(cpu_path)
    df_gpu = pd.read_feather(gpu_path)
    
    mat_cpu = df_cpu.iloc[:, 1:].values.astype(np.float32)
    mat_gpu = df_gpu.iloc[:, 1:].values.astype(np.float32)
    
    assert mat_cpu.shape == mat_gpu.shape, "Shape mismatch!"
    
    fc = mat_cpu.flatten()
    fg = mat_gpu.flatten()
    nonzero = (fc != 0) | (fg != 0)
    fc, fg = fc[nonzero], fg[nonzero]
    
    abs_diff = np.abs(fc - fg)
    corr = np.corrcoef(fc, fg)[0, 1]
    
    print(f"  Pearson correlation: {corr:.10f}")
    print(f"  Max abs diff:  {abs_diff.max():.6e}")
    print(f"  Mean abs diff: {abs_diff.mean():.6e}")
    print(f"  Exact matches: {(abs_diff == 0).sum():,}")
    
    return {
        'pearson_corr': float(corr),
        'max_abs_diff': float(abs_diff.max()),
        'verdict': 'PASS' if corr > 0.9999 else 'CHECK',
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--h5ad_path', required=True)
    p.add_argument('--output_dir', required=True)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--annotation', default=None)  # None = GPU fast path
    args = p.parse_args()
    
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    
    # Load data
    adata = sc.read_h5ad(args.h5ad_path)
    print(f"Cells: {adata.n_obs}, Genes: {adata.n_vars}")
    
    # Inject synthetic latent (skip training)
    adata = inject_synthetic_latent(adata, seed=args.seed)
    h5ad_out = out / f'{Path(args.h5ad_path).stem}_with_latent.h5ad'
    adata.write(h5ad_out)
    
    import shutil
    
    # --- CPU Run (with independent h5ad copy) ---
    cpu_dir = out / 'cpu'
    cpu_h5ad = cpu_dir / 'data.h5ad'
    cpu_dir.mkdir(exist_ok=True)
    shutil.copy2(h5ad_out, cpu_h5ad)
    
    t0 = time.time()
    # run_cpu(cpu_config_from(h5ad=cpu_h5ad, workdir=cpu_dir))
    cpu_time = time.time() - t0
    
    # --- GPU Run (with independent h5ad copy) ---
    gpu_dir = out / 'gpu'
    gpu_h5ad = gpu_dir / 'data.h5ad'
    gpu_dir.mkdir(exist_ok=True)
    shutil.copy2(h5ad_out, gpu_h5ad)
    
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    
    t0 = time.time()
    # run_gpu(gpu_config_from(h5ad=gpu_h5ad, workdir=gpu_dir))
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    gpu_time = time.time() - t0
    
    print(f"CPU: {cpu_time:.1f}s, GPU: {gpu_time:.1f}s, Speedup: {cpu_time/gpu_time:.1f}x")
    
    # --- Compare ---
    # results = compare_outputs(cpu_output_path, gpu_output_path)
    # results.update(cpu_time_s=cpu_time, gpu_time_s=gpu_time, speedup=cpu_time/gpu_time)
    # json.dump(results, open(out / 'results.json', 'w'), indent=2)


if __name__ == '__main__':
    main()
