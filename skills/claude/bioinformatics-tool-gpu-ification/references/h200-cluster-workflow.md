# H200 Cluster Workflow Reference

Practical patterns for running bioinformatics workloads on the PJLab H200 cluster via rjob.

---

## rjob Command Reference

### List jobs (filter by name)
```
rjob list 2>&1 | grep <job-name>
```

### View logs of a completed job
```
rjob logs job <job-name-with-timestamp>
```
NOT `rjob log <name>` (invalid action). NOT `rjob logs <name>` (needs `job` or `replica` target).

### Submit a job
```
rjob submit \
  --task-type=idle \
  --name=<friendly-name> \
  --enable-sshd \
  --gpu=1 \
  --memory=120000 \
  --cpu=16 \
  --mount=gpfs://gpfs2/liangxiuliang-2:/mnt/shared-storage-gpfs2/liangxiuliang-2 \
  --image=registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/<image>:<tag> \
  -P 1 \
  -- bash /path/to/script.sh
```

### Job states
- `Starting` / `Inqueue` — waiting for allocation
- `Running` — executing
- `Stopped` — killed (idle preemption, OOM, etc.)
- `Succeeded` / `Failed` — terminal

---

## Checkpoint Pattern for Long-Running Jobs

Idle pods get preempted by the scheduler. For any job expected to run >1 hour, use checkpoint files.

### Pattern
```bash
CHECK_DIR=/path/to/checkpoints
mkdir -p $CHECK_DIR

ck_done() { touch "$CHECK_DIR/$1"; }
ck_check() { [ -f "$CHECK_DIR/$1" ]; }

if ck_check "step1_done"; then
    echo "[STEP1] Already done, skipping"
else
    # ... run step 1 ...
    ck_done "step1_done"
fi
```

### Key rules
- Checkpoint directory MUST be on shared storage (gpfs1/gpfs2), NOT pod-local `/tmp`
- Write checkpoint AFTER step completes successfully
- If job is killed and resubmitted, checkpointed steps are skipped
- Use descriptive step names: `step2a_done`, `step2b_done`, etc.

### Resubmission
Same job command. The script auto-detects completed checkpoints and resumes from where it stopped. No manual intervention needed.

---

## GPFS Data Management

### Two storage pools
- **gpfs1** (`/mnt/shared-storage-user/liangxiuliang/`) — smaller quota (~100GB), original data location
- **gpfs2** (`/mnt/shared-storage-gpfs2/liangxiuliang-2/`) — larger quota (500GB+), preferred for working data

### Move data from gpfs1 to gpfs2
Submit a small pod that mounts BOTH gpfs1 and gpfs2:
```
rjob submit --task-type=idle --name=copy-data \
  --gpu=0 --memory=8000 --cpu=4 \
  --mount=gpfs://gpfs1/liangxiuliang:/mnt/shared-storage-user/liangxiuliang \
  --mount=gpfs://gpfs2/liangxiuliang-2:/mnt/shared-storage-gpfs2/liangxiuliang-2 \
  --image=<image> -P 1 \
  -- bash -c 'cp -r /mnt/shared-storage-user/liangxiuliang/<source> /mnt/shared-storage-gpfs2/liangxiuliang-2/<dest>'
```

### Single-mount preference
After data is on gpfs2, mount only gpfs2 in subsequent jobs. This avoids quota issues and simplifies paths.

---

## Script Upload Pattern

### Problem
Need to get a script from local machine onto gpfs2 for a pod to run.

### Solution: base64 encode → pod decode
```bash
# 1. Encode locally
cat script.sh | base64 | tr -d '\n' > /tmp/script_b64.txt

# 2. Submit upload pod
B64=$(cat /tmp/script_b64.txt)
rjob submit --task-type=idle --name=upload --gpu=0 --memory=2000 --cpu=1 \
  --mount=gpfs://gpfs2/liangxiuliang-2:/mnt/shared-storage-gpfs2/liangxiuliang-2 \
  --image=<image> -P 1 \
  -- bash -c "mkdir -p /mnt/.../scripts && echo ${B64} | base64 -d > /mnt/.../scripts/script.sh && chmod +x /mnt/.../scripts/script.sh"
```

### Alternative: heredoc (limited)
The heredoc through SSH → rjob has nesting and escaping issues with complex scripts. Prefer base64 for reliability.

---

## Pod Log Filtering

rjob pod logs contain heavy boilerplate (ssh-keygen, scp, sshd copies, PATH/LD_LIBRARY_PATH setup). Filter:

```bash
rjob logs job <name> 2>&1 | grep -v 'copy file success\|ssh-keygen\|sshd\|@caller\|@file\|@level\|@msg\|@timestamp\|PATH set\|LD_LIBRARY\|Exited\|Kill service\|process not'
```

Or grep for actual content markers:
```bash
rjob logs job <name> 2>&1 | grep -E 'STEP|Done:|PASS|FAIL|Error|copying|Verifying'
```

---

## Reading gpfs2 Logs from Outside

Since gpfs2 is only mounted inside pods (not on dev machine), read logs by submitting a lightweight pod:

```bash
rjob submit --task-type=idle --name=readlog --gpu=0 --memory=4000 --cpu=1 \
  --mount=gpfs://gpfs2/liangxiuliang-2:/mnt/shared-storage-gpfs2/liangxiuliang-2 \
  --image=<image> -P 1 \
  -- bash -c 'tail -50 /mnt/.../logs/e2e_run.log'
```

---

## Common Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| Job stuck STARTING | Mount path typo (`liangxiulinag`) | Double-check: correct is `liangxiuliang-2` |
| gpfs1 quota exceeded | ldscore outputs ~56GB | Use gpfs2 (500GB+) |
| Pod preempted mid-run | idle pod reclaimed | Checkpoint files + resubmit |
| Log file not found on dev | gpfs2 only mounted in pods | Submit readlog pod to access |
| `tee` fails in submit cmd | Log path doesn't exist on dev machine | Remove `tee` or use pod-mounted path |
| GPU scheduling delay | `--private-machine=no` on idle | Expected; use non-idle task type for faster scheduling |
| gsMap ldscore exits 0s | `--max_processes` not a valid arg for run_generate_ldscore | Remove `--max_processes`/`--num_processes` from ldscore command |
| Step completes but no output | Command failed silently (wrong args, missing data) | Always verify: check output files/dirs exist after each step before writing checkpoint |

---

## gsMap E2E Specific Notes

- Image: `registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.1`
- GPU mode: `GSMAP_DEVICE=gpu` env var (built into v1.1)
- CLI: use `gsmap` command (not `python3 -m gsMap`) in v1.1
- Memory: 120GB minimum (generate_ldscore peaks at ~80GB)
- Expected runtime: ~10-12 hours for full pipeline
- Data requirements: h5ad (~500MB), GWAS sumstats (~65MB), resource dir (~3.4GB)

---

## Watchdog Cron Pattern for Long-Running Jobs

When a job runs >8 hours, set up a cron watchdog that auto-resubmits on failure.

### Setup (via Hermes cronjob tool)
```
cronjob action=create name=<job>-watchdog schedule=30m
  prompt: Check job status. If Stopped/Failed/not-found → auto-resubmit. If Succeeded → report results and pause self.
  enabled_toolsets: ["terminal"]
```

### Watchdog behavior
- **Running/Starting/Inqueue** → brief status, no action
- **Stopped** → auto-resubmit (idle pod preemption is the most common cause)
- **Failed** → check error log first. If transient (OOM, preemption), resubmit. If code error, report it.
- **Succeeded** → read final results, report, pause the watchdog
- **Not found** → job vanished, resubmit

### Resubmission command
Same as original — the checkpoint script handles skipping completed steps:
```
rjob submit --task-type=idle --name=<same-name> --enable-sshd \
  --gpu=1 --memory=120000 --cpu=16 \
  --mount=gpfs://gpfs2/liangxiuliang-2:/mnt/shared-storage-gpfs2/liangxiuliang-2 \
  --image=<image> -P 1 -- bash /mnt/.../scripts/e2e_checkpoint.sh
```
