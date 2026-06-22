#!/bin/bash
# run_ldscore_parallel.sh — Chromosome-level parallel wrapper for gsMap STEP3
#
# Replaces serial `for chrom in 1..22` loop with concurrent execution.
# Each chromosome is independent (separate PLINK files, separate outputs).
# Uses --chrom N which gsMap natively supports.
#
# Usage:
#   MAX_PARALLEL=8 run_ldscore_parallel.sh \
#     --workdir /path/to/workdir \
#     --sample_name E16.5_E1S1.MOSTA \
#     --chrom all \
#     --bfile_root /path/to/plink/1000G.EUR.QC \
#     ... (all other gsmap run_generate_ldscore arguments)
#
# The --chrom argument is stripped and replaced with --chrom 1, --chrom 2, ...
# MAX_PARALLEL defaults to 8 if not set.
#
# On success: touches <workdir>/<sample_name>/generate_ldscore/<sample_name>_generate_ldscore.done
# On failure: reports which chromosomes failed, exits 1

set -euo pipefail

MAX_PARALLEL="${MAX_PARALLEL:-8}"

# Collect all arguments, stripping --chrom and its value
declare -a ARGS=()
SKIP_NEXT=false
SAMPLE_NAME=""
WORKDIR=""
for arg in "$@"; do
    if $SKIP_NEXT; then
        SKIP_NEXT=false
        continue
    fi
    case "$arg" in
        --chrom)
            SKIP_NEXT=true
            ;;
        --sample_name)
            ;;
        --workdir)
            ;;
        *)
            ARGS+=("$arg")
            ;;
    esac
    # Capture values for .done path
    if [ "$arg" = "--sample_name" ]; then
        SKIP_NEXT=false
        # Next arg will be the sample name but we need to capture differently
    fi
done

# Rebuild args properly and capture sample_name/workdir
declare -a FINAL_ARGS=()
i=1
while [ $i -le $# ]; do
    arg="${!i}"
    if [ "$arg" = "--chrom" ]; then
        i=$((i+2))  # skip --chrom and its value
        continue
    fi
    FINAL_ARGS+=("$arg")
    if [ "$arg" = "--sample_name" ]; then
        j=$((i+1))
        SAMPLE_NAME="${!j}"
    fi
    if [ "$arg" = "--workdir" ]; then
        j=$((i+1))
        WORKDIR="${!j}"
    fi
    i=$((i+1))
done

if [ -z "$WORKDIR" ] || [ -z "$SAMPLE_NAME" ]; then
    echo "ERROR: --workdir and --sample_name are required" >&2
    exit 1
fi

DONE_FILE="${WORKDIR}/${SAMPLE_NAME}/generate_ldscore/${SAMPLE_NAME}_generate_ldscore.done"

echo "[$(date)] Starting parallel generate_ldscore: 22 chromosomes, MAX_PARALLEL=$MAX_PARALLEL"
echo "[$(date)] Done file: $DONE_FILE"

# Remove stale done file
rm -f "$DONE_FILE"

FAILED_CHROMS=""
RUNNING=0

run_chromosome() {
    local chrom=$1
    local logfile="${WORKDIR}/${SAMPLE_NAME}/generate_ldscore/chr${chrom}.log"
    echo "[$(date)] Starting chromosome $chrom" | tee -a "$logfile"
    if gsmap run_generate_ldscore --chrom "$chrom" "${FINAL_ARGS[@]}" >> "$logfile" 2>&1; then
        echo "[$(date)] Chromosome $chrom DONE" | tee -a "$logfile"
        return 0
    else
        echo "[$(date)] Chromosome $chrom FAILED" | tee -a "$logfile"
        return 1
    fi
}

for chrom in $(seq 1 22); do
    run_chromosome "$chrom" &
    RUNNING=$((RUNNING + 1))

    if [ "$RUNNING" -ge "$MAX_PARALLEL" ]; then
        if wait -n; then
            RUNNING=$((RUNNING - 1))
        else
            FAILED_CHROMS="${FAILED_CHROMS} unknown,"
            RUNNING=$((RUNNING - 1))
        fi
    fi
done

# Wait for remaining jobs
while [ "$RUNNING" -gt 0 ]; do
    if wait -n; then
        RUNNING=$((RUNNING - 1))
    else
        FAILED_CHROMS="${FAILED_CHROMS} unknown,"
        RUNNING=$((RUNNING - 1))
    fi
done

if [ -n "$FAILED_CHROMS" ]; then
    echo "[$(date)] FAILED: some chromosomes failed: ${FAILED_CHROMS%,}" >&2
    exit 1
fi

touch "$DONE_FILE"
echo "[$(date)] All 22 chromosomes completed. Done file: $DONE_FILE"
