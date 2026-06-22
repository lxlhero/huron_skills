# gsMap v1.8 E2E GPU-vs-CPU Comparison

## Version summary

- **v1.8 image**: `registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.8`, built 2026-06-15
  - Self-contained: `/opt/e2e_gpu.sh` and `/opt/e2e_cpu.sh` baked into image
  - Bitarray pre-installed (cp311 manylinux x86_64 wheel)
  - latent_to_gene obsm key fallback fix
  - STEP3 parallel wrapper: `/opt/run_ldscore_parallel.sh`
  - WORKDIR_SUFFIX env var for run isolation: `${WORKDIR_SUFFIX:-v181}`
- **v1.7 image** (predecessor): Missing bitarray, STEP1 accepts different args. Still available but prefer v1.8.

## Why self-contained instead of GPFS external scripts

The "GPFS external scripts" pattern (scripts on GPFS2, rjob runs `bash /mnt/.../script.sh`) was tried first but failed due to GPFS path inconsistency across bastion instances. Different bastion gateway suffixes (`ailab-sdpdev.ws` vs `ailab-ma4agismall.ws`) route to different nodes with different GPFS client caches — files visible in one are invisible in another. Docker image-baked scripts proved more reliable.

Script iteration trade-off: Docker rebuild takes ~3 min (cached layers) vs instant GPFS edit. For stable E2E scripts, image-baked is the right choice. For rapid debug iteration, use the GPFS pattern temporarily, then bake into image once stable.

## v1.8 image composition

Build context on bastion (`/tmp/gsmap-build-v18/`):
- `Dockerfile`: FROM v1.7 base → COPY latent_to_gene.py fix → COPY bitarray .whl + pip install → COPY run_ldscore_parallel.sh → COPY e2e_gpu.sh + e2e_cpu.sh → chmod
- `latent_to_gene.py`: Patched with obsm key fallback
- `bitarray-3.8.1-cp311-cp311-manylinux2014_x86_64.whl`: Downloaded via `pip3 download bitarray --python-version 311 --platform manylinux2014_x86_64 --only-binary=:all:`
- `run_ldscore_parallel.sh`: Chromosome-level parallel STEP3 wrapper
- `e2e_gpu.sh`, `e2e_cpu.sh`: Full 5-step E2E scripts with WORKDIR_SUFFIX and timing

Build command:
```bash
DOCKER_BUILDKIT=0 docker build --no-cache --pull=false -t registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.8 .
```

**Always use `--no-cache` when modifying ANY file in build context** — Docker COPY layer caching can silently embed stale script content.

## WORKDIR_SUFFIX pattern

E2E scripts use dynamic workdir suffix to isolate runs:
```bash
W=/mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/workdir_gpu_${WORKDIR_SUFFIX:-v181}
```
Override via rjob `--set-env WORKDIR_SUFFIX=v182` for fresh runs without manual cleanup.

## E2E scripts (at /opt/ in v1.8 image)

### e2e_gpu.sh — GPU pipeline
- STEP1: find_latent_representations (CPU, `--data_layer count`, `--annotation annotation`)
- STEP2: latent_to_gene (CPU — no GSMAP_DEVICE; uses latents from STEP1)
- STEP3: generate_ldscore (`MAX_PARALLEL=8 /opt/run_ldscore_parallel.sh`)
- STEP4: spatial_ldsc (`GSMAP_DEVICE=gpu` for GPU, also runs CPU variant for comparison)
- STEP5: cauchy_combination (CPU)
- Prints timing summary at end

### e2e_cpu.sh — CPU baseline
- STEP1-2: Same as GPU (identical commands)
- STEP3: generate_ldscore (serial, `MAX_PARALLEL=1`)
- STEP4: spatial_ldsc (CPU only, no GSMAP_DEVICE)
- STEP5: cauchy_combination (CPU)
- Prints timing summary at end

## rjob submit commands (copy-paste ready, v1.8 image)

```bash
# GPU E2E
rjob submit \
  --task-type=idle --name=gsmap-e2e-gpu-v181 --enable-sshd \
  --gpu=1 --memory=122880 --cpu=16 \
  --mount=gpfs://gpfs2/liangxiuliang-2:/mnt/shared-storage-gpfs2/liangxiuliang-2 \
  --image=registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.8 \
  -P 1 -- bash /opt/e2e_gpu.sh

# CPU E2E (no GPU)
rjob submit \
  --task-type=idle --name=gsmap-e2e-cpu-v181 --enable-sshd \
  --memory=122880 --cpu=16 \
  --mount=gpfs://gpfs2/liangxiuliang-2:/mnt/shared-storage-gpfs2/liangxiuliang-2 \
  --image=registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.8 \
  -P 1 -- bash /opt/e2e_cpu.sh

# GPU E2E with custom suffix (avoids workdir conflict)
rjob submit \
  --task-type=idle --name=gsmap-e2e-gpu-v182 --enable-sshd \
  --gpu=1 --memory=122880 --cpu=16 \
  --mount=gpfs://gpfs2/liangxiuliang-2:/mnt/shared-storage-gpfs2/liangxiuliang-2 \
  --image=registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.8 \
  -P 1 --set-env WORKDIR_SUFFIX=v182 -- bash /opt/e2e_gpu.sh
```

## Comparison scope

E2E scripts compare:
- STEP1: Identical (no GPU toggle; both use CPU GNN training)
- STEP2: Identical (both CPU; GSMAP_DEVICE not set for STEP2 in GPU script)
- STEP3: Parallel (GPU) vs Serial (CPU)
- STEP4: GPU vs CPU spatial_ldsc
- STEP5: Identical (Cauchy combination)

The comparison covers STEP3 parallelism gains + STEP4 GPU acceleration.
