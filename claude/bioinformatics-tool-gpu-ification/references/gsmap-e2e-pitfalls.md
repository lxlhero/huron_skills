# gsMap E2E Testing Pitfalls (v1.3 → v1.4)

## Runtime patch IndentationError (v1.3)

**Symptom**: `gsmap run_generate_ldscore` fails with:
```
File "/opt/gsMap/src/gsMap/generate_ldscore.py", line 644
    if _ldscore_gpu is not None and os.environ.get("GSMAP_DEVICE") == "gpu":
    ^
IndentationError: expected an indented block after function definition on line 643
```

**Root cause**: `patch_gpu.py` at Docker build time does a string replace:
- Original: `    def _calculate_ldscore_from_weights(` (4-space indent, class method)
- Replacement: `def _calculate_ldscore_from_weights(*args, **kwargs):` (0-space indent)
- The replacement wrapper is at column 0 while it should be at column 4, making it a top-level function instead of a class method.

**Fix (v1.4)**: Create a pre-patched `generate_ldscore_patched.py` locally with:
1. GPU import header at the top of the file
2. GPU dispatch wrapper `_calculate_ldscore_from_weights()` that delegates to `_calculate_ldscore_from_weights_cpu()`
3. Validate with `import ast; ast.parse(content)` before building
4. `ADD generate_ldscore_patched.py /opt/gsMap/src/gsMap/generate_ldscore.py`
5. Remove generate_ldscore section from `patch_gpu.py`

## GPFS2 mount visibility trap

**Symptom**: Container reports `bash: /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/e2e_v13_gpu.sh: No such file or directory` even though `ls` on build host shows the file exists.

**Root cause**: Build host's `/mnt/shared-storage-gpfs2/` is `kataShared` virtiofs (different backend from container's `gpfs://gpfs2/` mount). Files written from build host are stored on a completely different storage system.

**Detection**: `df -h /mnt/shared-storage-gpfs2/` on build host shows `kataShared ... type virtiofs (ro,relatime)` — confirms it's not the real GPFS2.

**Fix**: 
1. Embed scripts as base64 in rjob command: `rjob submit ... -- bash -c 'echo "B64" | base64 -d | bash'`
2. Or SSH into a running container and write files from inside it

## Base64 inline deployment pattern

```bash
# Encode script
B64=$(base64 -w0 script.sh)

# Submit with embedded script
rjob submit \
  --name job-name \
  --task-type=idle \
  --enable-sshd \
  --image registry.h.pjlab.org.cn/.../image:tag \
  --gpu 1 \
  --memory 122880 \
  --mount gpfs://gpfs2/path:/mnt/mountpoint \
  -- bash -c 'echo "BASE64_CONTENT" | base64 -d | bash'
```

Max tested command length: ~14KB works fine through SSH + rjob.

## Bastion SSH suffix routing (GPFS view mismatch)

**Symptom**: User confirms files exist at `/mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/` but agent's SSH sees different content at the same path (only `build/ docker-build-v1.2/` instead of `workdir_gpu/ workdir_cpu_fresh/`).

**Root cause**: The bastion pool has multiple instances behind `h.pjlab.org.cn`. The SSH username suffix determines which pool you hit:
- `huron-dev-1.liangxiuliang+root.ailab-sdpdev.ws@h.pjlab.org.cn` → routes to sdpdev pool, sees LIMITED GPFS view (missing workdirs)
- `huron-dev-1.liangxiuliang+root.ailab-ma4agismall.ws@h.pjlab.org.cn` → routes to ma4agismall pool, sees FULL GPFS workdirs (RECOMMENDED)

**Fix**: If files are confirmed to exist by user but invisible to SSH, try the `ailab-ma4agismall.ws` suffix. The `.ws` naming corresponds to the rjob namespace — use the suffix matching the namespace where jobs were submitted.

**Detection**: `ls /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/` shows different file lists from different SSH suffixes. If user sees workdirs but agent sees only build files, switch suffix.

## rjob memory unit

`--memory` expects integer MiB. `--memory 120GB` → "invalid int value". Correct: `--memory 122880` (120 × 1024).

## rjob command delimiter

Uses `--` not `--command`: `rjob submit [options] -- <command line>`.

## Don't delete workdir until user confirms

**Pitfall**: After E2E comparison completes, deleting the CPU (reference) workdir to free disk space is logical — but the user may want to re-examine intermediate outputs or run additional comparisons first. Deleting prematurely means the original reference is lost forever.

**Fix**: Wait for explicit user confirmation before deleting either workdir. Even if disk quota is tight, present the delete as a proposed action, not an automatic one.

## Amdahl's Law inevitably caps GPU speedup

**Pitfall**: Expecting a GPU-accelerated step to deliver proportional end-to-end speedup. If the GPU-accelerated step accounts for only 3% of total runtime (e.g., spatial_ldsc in gsMap small-sample E2E), even infinite GPU speedup can't improve total time by more than 3%.

**Formula**: Max speedup = 1 / (F_non_gpu + F_gpu / S_gpu), where F_gpu is the fraction of runtime spent in GPU-accelerated code and S_gpu is that step's acceleration factor.

**Diagnostic**: Before GPU-ifying, compute the Amdahl ceiling. If it's under 1.1×, the effort is about precision validation, not speed. Amdahl ceilings above 2× require the GPU-accelerated step to dominate total runtime (>50% fraction).

**gsMap example**: STEP4 spatial_ldsc = 3.9% of runtime, accelerated 1.5× → Amdahl ceiling = 1.01×. Real speed comes from either (a) making spatial_ldsc the dominant step (large datasets), or (b) GPU-ifying the 87% step (generate_ldscore, but it's I/O-bound).
