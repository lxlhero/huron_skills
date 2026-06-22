# gsMap v1.8.3 E2E GPU vs CPU Plan (Claude Code v2.1.63)

Generated: 2026-06-16. Context: v1.6 had STEP3 serial, E2E CPU 1h49m vs GPU 1h44m (1.05×).
Goal: parallel STEP3 (MAX_PARALLEL=4) on BOTH sides to reduce the bottleneck, making GPU STEP4+5 acceleration visible.

## Job Config

| Parameter | CPU Job | GPU Job |
|-----------|---------|---------|
| Image | v1.8.3 | v1.8.3 |
| GPU | 0 | 1 |
| CPU | 16 | 16 |
| Memory | 64GB (64000 MiB) | 64GB |
| Workdir | workdir_cpu_v183_e2e | workdir_gpu_v183_e2e |
| STEP3 | MAX_PARALLEL=4 | MAX_PARALLEL=4 |
| STEP2 | GSMAP_DEVICE=cpu | GSMAP_DEVICE=gpu |
| STEP4 | GSMAP_DEVICE=cpu | GSMAP_DEVICE=gpu |

## Amdahl's Law Projection

| Step | CPU serial (v1.6) | CPU parallel (expected) | GPU speedup | GPU parallel (expected) |
|------|-------------------|------------------------|-------------|------------------------|
| STEP1-2 | ~10 min | ~10 min | ~1× | ~10 min |
| STEP3 | ~66 min | ~25-40 min | ~1× | ~25-40 min |
| STEP4 | ~3 min | ~3 min | ~1.5× | ~2 min |
| STEP5 | ~7 min | ~7 min | ~1.75× | ~4 min |
| **Total** | ~86 min | ~45-60 min | — | ~41-56 min |

With parallel STEP3 reducing the non-GPU-able bottleneck, GPU acceleration of STEP4+5
becomes a larger fraction of total runtime (from ~4% to ~10-15%), making the speedup
more visible at ~1.1-1.3× E2E.

## Post-Completion Steps

1. Check job status → extract wall-clock times per step
2. Precision comparison:
   - spatial_ldsc: beta Pearson > 0.999
   - cauchy_combination: p_cauchy Pearson > 0.999
3. Compare CPU vs GPU timing
4. Format as Feishu report

## Quota Strategy

When GPU project quota is full (e.g., 89/88):
1. Keep only CPU job running — get baseline data
2. Use CPU data + historical GPU ratios to estimate GPU time
3. Wait for quota to free before submitting GPU job
4. Never let both jobs sit pending with zero data output

## Submission Pattern

All jobs use `bash -c` inline commands (user preference — no script files):

```bash
rjob submit --task-type=normal -P 1 \
  --charged-group=ma4agismall_gpu --namespace=ailab-ma4agismall \
  --private-machine=group --enable-sshd \
  --cpu=16 --memory=64000 --gpu=0 \
  --mount=gpfs://gpfs2/liangxiuliang-2:/mnt/shared-storage-gpfs2/liangxiuliang-2 \
  --image=registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.8.3 \
  --name=gsmap-e2e-cpu-v183 \
  -- bash -c '...'
```

## Pitfalls Discovered

- `$` escaping in bash -c: `\$DATA` needed to survive SSH → rjob → pod chain
- Workdir symlinks break when source cleaned → always use fresh independent workdirs
- GPFS not visible from bastion → verify via reader pod, not bastion shell
- `rjob logs` syntax: `rjob logs job <name> --namespace <ns>` (NOT `rjob logs <name>`)
- Claude Code invocation: `echo "prompt" | claude -p "$(cat)"` (stdin pipe, not command arg)
