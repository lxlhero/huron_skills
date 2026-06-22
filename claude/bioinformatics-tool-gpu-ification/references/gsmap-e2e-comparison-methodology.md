# gsMap End-to-End GPU vs CPU Comparison Methodology

Verified 2026-06-16 with gsmap-gpu:v1.8.3 on H200.

## Design Principle

After GPU-accelerating STEP4+5, the E2E speedup was negligible (1.04x) because STEP3 dominated at 62% of runtime. The solution: parallelize STEP3 first, then compare E2E with both versions using parallel STEP3, so GPU acceleration on STEP4+5 becomes the differentiator.

## Pipeline

```
Version A (CPU):  STEP1-3(parallel) → STEP4(CPU) → STEP5(CPU)
Version B (GPU):  STEP1-3(parallel) → STEP4(GPU) → STEP5(GPU)
```

Both versions share identical STEP1-3 results via hard-link.

## Steps

### 1. Run STEP3 parallel, verify precision

```bash
# Serial (reference)
rjob submit --name gsmap-step3-serial --gpu=0 --cpu=8 --memory 64000 \
  --image=registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.8.3 \
  -- bash -c '...'

# Parallel (4 workers)
rjob submit --name gsmap-step3-parallel --gpu=0 --cpu=8 --memory 64000 \
  --image=registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.8.3 \
  -- bash -c '...'
```

**Verified**: 22/22 chromosomes MD5 identical (w_ld weights + baseline LD feathers).

### 2. Clean serial STEP3, submit E2E jobs

Delete serial generate_ldscore/ (200G+ freed) after MD5 confirmation.

```bash
# CPU E2E (reuses parallel STEP3)
rjob submit --name gsmap-e2e-cpu --gpu=0 --cpu=16 --memory 64000 \
  --image=... -- bash -c '
  GSMAP_DEVICE=cpu gsmap run_spatial_ldsc ...   # STEP4
  gsmap run_cauchy_combination ...              # STEP5
'

# GPU E2E (hard-links STEP3, runs STEP4+5 on GPU)
rjob submit --name gsmap-e2e-gpu --gpu=1 --cpu=16 --memory 64000 \
  --image=... -- bash -c '
  cp -rl $SRC_WD/$SAMPLE/{find_latent,latent_to_gene,generate_ldscore} $GPU_WD/$SAMPLE/
  GSMAP_DEVICE=gpu gsmap run_spatial_ldsc ...    # STEP4 GPU
  gsmap run_cauchy_combination ...               # STEP5
'
```

### 3. Collect timing and compare

Monitor both jobs simultaneously. Collect per-step timing from logs.

### 4. Verify precision

```bash
rjob submit --name gsmap-compare --gpu=0 --cpu=2 --memory 16000 \
  --image=... -- bash -c '
python3 -c "
import pandas as pd, numpy as np
# Load CPU and GPU output CSVs
cpu = pd.read_csv(\"cpu_path.csv.gz\")
gpu = pd.read_csv(\"gpu_path.csv.gz\")
for col in gpu.select_dtypes(\"number\").columns:
    corr = np.corrcoef(gpu[col], cpu[col])[0,1]
    print(f\"{col}: Pearson={corr:.8f}\")
"
'
```

## Key Data

| Phase | STEP3 Serial | STEP3 Parallel (4w) | Speedup |
|-------|-------------|---------------------|---------|
| STEP3  | ~45 min    | ~40 min             | 1.12x   |
| STEP3 (projected 8w) | 45 min | ~22 min | 2x+ |

With 8 workers, STEP3 drops from 45min→~22min, increasing STEP4 E2E share from 4%→20%+, making GPU acceleration visible.

## Pitfalls

1. **False-positive FAILED**: `run_ldscore_parallel.sh` reports chromosomes as FAILED even when output exists and is MD5-identical. Verify with file existence + MD5, not job status.
2. **Bash escaping**: Python f-strings with `{braces}` inside `bash -c` cause syntax errors. Use `python3 -c "..."` with simple calls.
3. **Disk space**: Serial STEP3 is 200G+. Delete after MD5 confirmation before E2E runs.
4. **Namespace**: Always `--namespace ailab-ma4agismall` for rjob commands.
