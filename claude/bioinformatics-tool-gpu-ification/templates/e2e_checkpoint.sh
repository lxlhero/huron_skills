#!/bin/bash
# Template: Checkpoint-based pipeline script for H200 cluster jobs
# Copy and customize for your tool.
#
# Usage:
#   1. Set paths in the configuration section
#   2. Fill in each step's commands
#   3. Submit: rjob submit ... -- bash /path/to/this_script.sh
#   4. If killed, resubmit same command — completed steps are skipped

set -e

export PATH=/opt/conda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# ============================================================
# CONFIGURATION — edit these
# ============================================================
SHARED_BASE=/mnt/shared-storage-gpfs2/your-path    # gpfs2 mount root
LOG_DIR=$SHARED_BASE/logs
CHECK_DIR=$SHARED_BASE/logs/checkpoints

# Tool-specific paths
DATA_DIR=$SHARED_BASE/data
RES_DIR=$SHARED_BASE/resource
SAMPLE=your_sample

mkdir -p $LOG_DIR $CHECK_DIR

# ============================================================
# CHECKPOINT HELPERS — do not modify
# ============================================================
log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a $LOG_DIR/pipeline.log; }
ck_done() { touch "$CHECK_DIR/$1"; }
ck_check() { [ -f "$CHECK_DIR/$1" ]; }

log "========== Pipeline started: $(date) =========="

# Verify environment
python3 -c "
import torch
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    print(f'VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB')
"

# ============================================================
# STEP 1: <describe step>
# ============================================================
if ck_check "step1_done"; then
    log "[STEP1] Already done, skipping"
else
    log "[STEP1] Running..."
    T1=$(date +%s)
    # === YOUR COMMAND HERE ===
    # gsmap run_xxx --workdir $WORKDIR --sample_name $SAMPLE ...
    # =========================
    T2=$(date +%s)
    log "[STEP1] Done: $((T2-T1))s"
    ck_done "step1_done"
fi

# ============================================================
# STEP 2: <describe step>
# ============================================================
if ck_check "step2_done"; then
    log "[STEP2] Already done, skipping"
else
    log "[STEP2] Running..."
    T1=$(date +%s)
    # === YOUR COMMAND HERE ===
    # =========================
    T2=$(date +%s)
    log "[STEP2] Done: $((T2-T1))s"
    ck_done "step2_done"
fi

# ============================================================
# Add more steps as needed (STEP3, STEP4, ...)
# ============================================================

# ============================================================
# FINAL: Comparison / validation
# ============================================================
if ck_check "compare_done"; then
    log "[COMPARE] Already done, skipping"
else
    log "[COMPARE] Running comparison..."
    python3 << 'PYEOF'
import pandas as pd
import numpy as np
# === YOUR COMPARISON CODE HERE ===
# Compare CPU vs GPU outputs, compute Pearson, MAE, etc.
print("Comparison: customize this block")
PYEOF
    ck_done "compare_done"
fi

log "========== Pipeline complete: $(date) =========="
