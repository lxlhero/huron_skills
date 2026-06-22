#!/usr/bin/env python3
"""gsMap CPU vs GPU cauchy combination 精度对比（可复用的对比脚本模板）"""
import gzip, sys, os
import numpy as np
import pandas as pd
from scipy.stats import pearsonr

base = "/mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap"
cpu_f = f"{base}/cauchy_cpu.csv.gz"
gpu_f = f"{base}/cauchy_gpu.csv.gz"

print("=== 文件大小 ===")
for label, f in [("CPU", cpu_f), ("GPU", gpu_f)]:
    size = os.path.getsize(f)
    print(f"{label}: {size:,} bytes ({size/1024:.1f} KB)")

print("\n=== 加载数据 ===")
cpu = pd.read_csv(cpu_f, compression='gzip')
gpu = pd.read_csv(gpu_f, compression='gzip')
print(f"CPU: {cpu.shape[0]} rows × {cpu.shape[1]} cols")
print(f"GPU: {gpu.shape[0]} rows × {gpu.shape[1]} cols")
print(f"\nCPU 列: {list(cpu.columns)}")
print(f"GPU 列: {list(gpu.columns)}")

# Merge on gene name column (try common names)
gene_col = None
for c in ['gene', 'Gene', 'gene_name', 'Gene_name', 'GENE', 'symbol', 'Symbol']:
    if c in cpu.columns and c in gpu.columns:
        gene_col = c
        break

if gene_col is None:
    for c in cpu.columns:
        if cpu[c].dtype == object and c in gpu.columns:
            gene_col = c
            break

print(f"\nGene column: {gene_col}")

merged = cpu.merge(gpu, on=gene_col, how='inner', suffixes=('_cpu', '_gpu'))
print(f"Merged: {len(merged)} genes (inner join)")

# Find numeric columns for comparison
num_cols = []
for c in cpu.columns:
    if c == gene_col:
        continue
    if c in gpu.columns and cpu[c].dtype in (np.float64, np.float32, np.int64, np.int32):
        num_cols.append(c)

print(f"\n可比较数值列 ({len(num_cols)}): {num_cols}")

print("\n" + "=" * 70)
print("=== 精度对比 ===")
print("=" * 70)

results = []
for col in num_cols:
    cpu_vals = merged[f"{col}_cpu"].astype(float)
    gpu_vals = merged[f"{col}_gpu"].astype(float)

    mask = np.isfinite(cpu_vals) & np.isfinite(gpu_vals)
    if mask.sum() < 2:
        continue

    cpu_vals = cpu_vals[mask]
    gpu_vals = gpu_vals[mask]

    pearson_r, pearson_p = pearsonr(cpu_vals, gpu_vals)
    max_diff = np.max(np.abs(cpu_vals - gpu_vals))
    mean_diff = np.mean(np.abs(cpu_vals - gpu_vals))

    results.append({
        'column': col,
        'N': mask.sum(),
        'pearson_r': pearson_r,
        'pearson_p': pearson_p,
        'max_abs_diff': max_diff,
        'mean_abs_diff': mean_diff,
    })

    print(f"\n[{col}] N={mask.sum()}")
    print(f"  Pearson r = {pearson_r:.10f}   (p={pearson_p:.2e})")
    print(f"  Max |diff| = {max_diff:.10e}")
    print(f"  Mean |diff| = {mean_diff:.10e}")

print("\n" + "=" * 70)
print("=== 汇总 ===")
print("=" * 70)

for r in results:
    status = "PASS" if r['pearson_r'] > 0.9999 else "FAIL"
    print(f"  {r['column']:30s} r={r['pearson_r']:.10f}  max_diff={r['max_abs_diff']:.2e}  {status}")

all_pass = all(r['pearson_r'] > 0.9999 for r in results)
print(f"\n总体: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")
