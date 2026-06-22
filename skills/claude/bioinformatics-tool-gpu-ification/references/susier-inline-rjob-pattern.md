# susieR Inline rjob Pattern (base64-embedded scripts)

## Why

Per user iron rule: all rjob commands must use `bash -c '...'` inline — no external script files on GPFS. R scripts (profile.R, gen_data.R) are base64-encoded and embedded directly in the rjob command.

## ⚠️ CRITICAL: SSH quoting caveat

**This base64-inline pattern FAILS when commands go through SSH.** The triple layer (SSH outer quotes → rjob parser → bash -c) mangles nested quotes, dollar signs, and base64 newlines. Attempts result in:
- Single quotes inside single quotes → premature termination
- `$SHARED`, `${GEN_B64}` variables expanded on bastion, not pod
- Base64 strings truncated by SSH line splitting

**When submitting via SSH bastion, use the GPFS-write pattern instead (pitfall #53 in SKILL.md):**
1. Write the script to GPFS via `ssh ... 'cat > /mnt/.../run.sh << '"'"'EOF'"'"'...EOF'`
2. Submit rjob pointing to the GPFS file: `rjob submit ... -- bash /mnt/.../run.sh`

This adds ~30s overhead vs 20+ min of failed inline-SSH retries.

## Template: rjob submit command (local, no SSH)

Use this template when submitting rjob from a local terminal (not through SSH):

```bash
# 1. Base64-encode your R scripts
PROFILE_B64=$(base64 -i profile.R | tr -d '\n')
GEN_B64=$(base64 -i gen_data.R | tr -d '\n')

# 2. Submit rjob with inline scripts
rjob submit \
  --task-type normal \
  --priority 9 \
  --name susier-profile-medium \
  --namespace ailab-ma4agismall \
  --cpu 8 \
  --memory 60000 \
  --gpu 0 \
  --charged-group ma4agismall_gpu \
  --private-machine group \
  --mount gpfs://gpfs2/liangxiuliang-2:/mnt/shared-storage-gpfs2/liangxiuliang-2 \
  --image registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/susier-gpu:20260617-base \
  -- bash -c '
set -e -o pipefail

# Verify environment
export LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/cuda/lib64:$LD_LIBRARY_PATH
export OPENBLAS_NUM_THREADS=8
Rscript -e "cat(\"R:\", as.character(getRversion()), \"\\n\"); library(susieR); library(reticulate)"
python3 -c "import torch; print(f\"PyTorch {torch.__version__}\")"

# Paths
SHARED="/mnt/shared-storage-gpfs2/liangxiuliang-2/susieR"
DATADIR="${SHARED}/data"
PROFILEDIR="${SHARED}/profile"
mkdir -p "${DATADIR}" "${PROFILEDIR}"

# Step A: Generate benchmark data
echo "${GEN_B64}" | base64 -d > /tmp/gen_data.R
Rscript /tmp/gen_data.R medium

# Step B: Run profiling
echo "${PROFILE_B64}" | base64 -d > /tmp/profile.R
Rscript /tmp/profile.R --data "${DATADIR}/bench_5k_10k_L10.rds"

# Step C: Save results
cp "${DATADIR}/bench_5k_10k_L10_profile.json" "${PROFILEDIR}/"
echo "Done: ${PROFILEDIR}/bench_5k_10k_L10_profile.json"
'
```

## Template: rjob submit via SSH (use this — NOT the base64-inline pattern)

```bash
ssh ... '

# Step 1: Write the profile script to GPFS
cat > /mnt/shared-storage-gpfs2/liangxiuliang-2/susieR/run_profile.sh << '"'"'SCRIPTEOF'"'"'
#!/bin/bash
set -e -o pipefail

export LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/cuda/lib64:$LD_LIBRARY_PATH
export OPENBLAS_NUM_THREADS=8

SHARED="/mnt/shared-storage-gpfs2/liangxiuliang-2/susieR"
DATADIR="${SHARED}/data"
PROFILEDIR="${SHARED}/profile"
mkdir -p "${DATADIR}" "${PROFILEDIR}"

Rscript -e "cat(\"R:\", as.character(getRversion()), \"\n\"); library(susieR); library(reticulate)"
python3 -c "import torch; print(f\"PyTorch {torch.__version__}\")"

# Generate data
Rscript /opt/susieR/gen_data.R medium

# Profile
Rscript /opt/susieR/profile.R --data "${DATADIR}/bench_5k_10k_L10.rds"

cp "${DATADIR}/bench_5k_10k_L10_profile.json" "${PROFILEDIR}/"
echo "Done: ${PROFILEDIR}/bench_5k_10k_L10_profile.json"
SCRIPTEOF

chmod +x /mnt/shared-storage-gpfs2/liangxiuliang-2/susieR/run_profile.sh

# Step 2: Submit rjob
rjob submit \
  --task-type normal \
  --priority 9 \
  --name susier-profile-medium \
  --namespace ailab-ma4agismall \
  --cpu 8 \
  --memory 60000 \
  --gpu 0 \
  --charged-group ma4agismall_gpu \
  --private-machine group \
  --mount gpfs://gpfs2/liangxiuliang-2:/mnt/shared-storage-gpfs2/liangxiuliang-2 \
  --image registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/susier-gpu:20260617-base \
  -- bash /mnt/shared-storage-gpfs2/liangxiuliang-2/susieR/run_profile.sh
'
```

## Size limits

- rjob command max: ~14KB (from gsMap pitfall #16)
- profile.R base64: ~5.8KB (143 lines of R)
- gen_data.R base64: ~2.9KB (60 lines of R)
- Together ~8.7KB + bash boilerplate ~2KB = ~11KB total — well within limit

## Key flags

| Flag | Value | Why |
|------|-------|-----|
| `--gpu 0` | No GPU | Step 1 is CPU profiling only |
| `--cpu 8` | 8 cores | susieR's Armadillo BLAS uses multithreading |
| `--memory 60000` | 60GB | X matrix 400MB, room for BLAS workspace |
| `--private-machine group` | Exclusive | Avoid sharing with other jobs |
| `--charged-group ma4agismall_gpu` | Required | R project uses this group |
| `--namespace ailab-ma4agismall` | Required | Cross-partition access |

## Reticulate verification

Always verify the R→Python bridge in the rjob preamble:
```bash
Rscript -e 'library(reticulate); py_run_string("import torch; print(torch.__version__)")'
```
