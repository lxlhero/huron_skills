# gsMap STEP 3 Serial vs Parallel Comparison

## Purpose

Compare serial vs parallel (per-chromosome) execution of gsMap's `generate_ldscore` step. Both modes run on CPU; the contrast is parallelism strategy, not hardware. This determines whether the parallel wrapper (`run_ldscore_parallel.sh`) can match serial output exactly while delivering a real speedup.

## Methodology

### Workdir Strategy

- **Serial workdir** (`workdir_cpu_v181`): Full STEP 1+2+3 run. All outputs live here.
- **Parallel workdir** (`workdir_cpu_v181_parallel`): `E16.5_E1S1.MOSTA/` symlinked to serial workdir so STEP 1+2 outputs are shared. ldscore output is written to a subdirectory within the parallel workdir (independent from serial).

This preserves the serial workdir as the gold-standard reference while avoiding wasteful recomputation of STEP 1+2.

### Phase Pipeline

1. **STEP 1+2** — Run find_latent_representations + latent_to_gene into `workdir_cpu_v181`
2. **Init parallel workdir** — `rm -rf workdir_cpu_v181_parallel && mkdir && ln -sfn workdir_cpu_v181/E16.5_E1S1.MOSTA workdir_cpu_v181_parallel/E16.5_E1S1.MOSTA`
3. **Serial STEP 3** — `gsmap run_generate_ldscore --chrom all` → writes to serial workdir
4. **Parallel STEP 3** — `MAX_PARALLEL=16 /opt/run_ldscore_parallel.sh --chrom all` → writes to parallel workdir
5. **Comparison** — Python script that reads both ldscore directories, compares per-chromosome

### Precision Metrics

- **Pearson r** per chromosome, on the LD-score value column (not metadata)
- **Max absolute diff** and **mean absolute diff**
- Pass threshold: max_diff < 1e-6 per chromosome, all 22 chromosomes OK

## Scripts

All scripts live on GPFS at `/mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/` and are invoked via rjob. Copy-paste paths:

| Script | Purpose | Local source |
|--------|---------|--------------|
| `e2e_step12.sh` | STEP 1+2 only → workdir_cpu_v181 | `docker/e2e_step12.sh` |
| `init_parallel_workdir.sh` | Creates parallel workdir with symlinks | `docker/init_parallel_workdir.sh` |
| `e2e_step3_serial.sh` | Serial STEP 3 runner | `docker/e2e_step3_serial.sh` |
| `e2e_step3_parallel.sh` | Parallel STEP 3 runner (MAX_PARALLEL=16) | `docker/e2e_step3_parallel.sh` |
| `compare_ldscore.py` | Precision comparison (Python) | `docker/compare_ldscore.py` |

### e2e_step12.sh — Critical GPFS wait loop

The script MUST wait for GPFS to become available before reading input files:

```bash
BASE=/mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap
RES=/mnt/shared-storage-gpfs2/liangxiuliang-2/gsMap_resource
H5AD=$BASE/gsMap_example_data/ST/E16.5_E1S1.MOSTA.h5ad
HOMOLOG=$RES/homologs/mouse_human_homologs.txt

log() { echo "[$(date '+%H:%M:%S')] $1"; }
START_TIME=$(date +%s)

log "Waiting for GPFS data availability..."
for i in $(seq 1 30); do
  if [ -f "$H5AD" ] && [ -f "$HOMOLOG" ]; then
    log "GPFS data ready after ${i}s"
    break
  fi
  sleep 1
done
if [ ! -f "$H5AD" ]; then
  log "ERROR: H5AD not found: $H5AD"
  exit 1
fi
```

Also: record `START_TIME` at the top and compute wall time at the end as `$((END_TIME - START_TIME))`. Do NOT use `date -r` on a just-created file.

### e2e_step3_parallel.sh — Correct run_ldscore_parallel.sh path

The parallel wrapper is at `/opt/run_ldscore_parallel.sh` in the image (NOT `/opt/gsMap/src/gsMap/run_ldscore_parallel.sh`). The gsmap Dockerfile line is: `COPY gsmap/run_ldscore_parallel.sh /opt/run_ldscore_parallel.sh`.

## Rjob Commands (copy-paste ready)

All use image `registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.8.3`.

Common prefix (add to all):
```
rjob submit --task-type=normal --priority=9 \
  --charged-group=ma4agismall_gpu --namespace=ailab-ma4agismall \
  --private-machine=group --enable-sshd \
  --mount=gpfs://gpfs2/liangxiuliang-2:/mnt/shared-storage-gpfs2/liangxiuliang-2 \
  --image registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.8.3
```

| Phase | --cpu | --memory | --name | Command |
|-------|-------|----------|--------|---------|
| STEP 1+2 | 16 | 120000 | gsmap-step12 | `-- bash /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/e2e_step12.sh` |
| Init parallel | 2 | 4000 | gsmap-init-par | `-- bash /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/init_parallel_workdir.sh` |
| Serial STEP 3 | 16 | 120000 | gsmap-step3-serial | `-- bash /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/e2e_step3_serial.sh` |
| Parallel STEP 3 | 16 | 120000 | gsmap-step3-parallel | `-- bash /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/e2e_step3_parallel.sh` |
| Precision compare | 8 | 32000 | gsmap-compare | `-- bash -c 'python3 /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/compare_ldscore.py 2>&1'` |

## Results Location (GPFS)

```
workdir_cpu_v181/serial_result.txt         → MODE=serial, WALL_SECONDS=...
workdir_cpu_v181_parallel/parallel_result.txt → MODE=parallel, WALL_SECONDS=...
workdir_cpu_v181/precision_report.csv      → Per-chromosome comparison
workdir_cpu_v181/precision_verdict.txt     → PASS/WARN summary
```

## Pitfalls

- **GPFS mount delay on pod startup** (skill pitfall #35): Always include a 30s max wait loop.
- **rjob list requires `--namespace ailab-ma4agismall`**: Without it, jobs are invisible.
- **rjob logs only works while pod is alive**: Pods are deleted on completion. Use reader pods to inspect GPFS results.
- **run_ldscore_parallel.sh path**: `/opt/run_ldscore_parallel.sh`, NOT `/opt/gsMap/src/gsMap/run_ldscore_parallel.sh`.
- **Symlink race**: The parallel workdir symlink must be created AFTER STEP 1+2 completes but BEFORE STEP 3 starts.
- **Wall time calculation**: Record `START_TIME=$(date +%s)` before work, compute at end — don't use file timestamps.
- **False-positive FAILED (skill pitfall #38)**: `run_ldscore_parallel.sh` reports chromosomes as FAILED even when output is complete and MD5-identical to serial. In 2026-06-16 testing: 16/22 chromosomes reported FAILED, but all 22 w_ld + 22 baseline files passed MD5 comparison. NEVER re-run based on orchestrator exit code — always verify with `ls w_ld/*.gz | wc -l` (should be 22) and md5sum against reference.
