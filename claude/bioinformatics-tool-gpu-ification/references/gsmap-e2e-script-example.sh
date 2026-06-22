#!/bin/bash
# gsMap end-to-end checkpoint script — real working example from 2026-06-10
# Runs CPU vs GPU full pipeline (STEP1→STEP6) with precision comparison
# Image: gsmap-gpu:v1.1, GPU mode via GSMAP_DEVICE=gpu
set -e

export PATH=/opt/conda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# ============================================================
# Paths (all on gpfs2 — single mount)
# ============================================================
DATA=/mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap
RES=/mnt/shared-storage-gpfs2/liangxiuliang-2/gsMap_resource
SAMPLE=E16.5_E1S1.MOSTA
ANNOT=annotation
TRAIT=IQ
LOG_DIR=$DATA/logs
CHECK_DIR=$DATA/logs/checkpoints
CPU_WORKDIR=$DATA/workdir_cpu
GPU_WORKDIR=$DATA/workdir_gpu
H5AD=$DATA/gsMap_example_data/ST/${SAMPLE}.h5ad
SUMSTATS=$DATA/gsMap_example_data/GWAS/IQ_NG_2018.sumstats.gz

mkdir -p $LOG_DIR $CHECK_DIR

log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a $LOG_DIR/e2e_run.log; }
ck_done() { touch "$CHECK_DIR/$1"; }
ck_check() { [ -f "$CHECK_DIR/$1" ]; }

# ============================================================
# Environment check
# ============================================================
log "========== gsMap E2E Checkpoint Run =========="
log "Started: $(date)"
python3 -c "
import torch
print(f'CUDA: {torch.cuda.is_available()}, GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')
" 2>&1 | tee -a $LOG_DIR/e2e_run.log

# ============================================================
# STEP1: find_latent_representations (shared)
# ============================================================
if ck_check "step1_done"; then
    log "[STEP1] Already done, skipping"
else
    log "[STEP1] find_latent_representations"
    T1=$(date +%s)
    gsmap run_find_latent_representations \
        --workdir $CPU_WORKDIR \
        --sample_name $SAMPLE \
        --input_hdf5_path $H5AD \
        --annotation $ANNOT \
        --data_layer count 2>&1 | tee -a $LOG_DIR/e2e_run.log
    T2=$(date +%s)
    log "[STEP1] Done: $((T2-T1))s"
    ck_done "step1_done"
fi

# Copy latent h5ad to GPU workdir
GPU_LATENT_DIR=$GPU_WORKDIR/$SAMPLE/find_latent_representations
CPU_LATENT=$CPU_WORKDIR/$SAMPLE/find_latent_representations/${SAMPLE}_add_latent.h5ad
mkdir -p $GPU_LATENT_DIR
if [ ! -f "$GPU_LATENT_DIR/${SAMPLE}_add_latent.h5ad" ]; then
    cp $CPU_LATENT $GPU_LATENT_DIR/
    log "[STEP1] Copied latent h5ad to GPU workdir"
fi

# ============================================================
# STEP2a: latent_to_gene CPU (original)
# ============================================================
if ck_check "step2a_done"; then
    log "[STEP2a] Already done, skipping"
    T_CPU_LTG=$(grep "CPU done:" $LOG_DIR/e2e_run.log | tail -1 | grep -oP '\d+')
else
    log "[STEP2a] latent_to_gene CPU"
    T1=$(date +%s)
    gsmap run_latent_to_gene \
        --workdir $CPU_WORKDIR \
        --sample_name $SAMPLE \
        --annotation $ANNOT \
        --latent_representation latent_GVAE \
        --homolog_file $RES/homologs/mouse_human_homologs.txt 2>&1 | tee -a $LOG_DIR/e2e_run.log
    T2=$(date +%s)
    T_CPU_LTG=$((T2-T1))
    log "[STEP2a] CPU done: ${T_CPU_LTG}s"
    ck_done "step2a_done"
fi

# ============================================================
# STEP2b: latent_to_gene GPU (GSMAP_DEVICE=gpu)
# ============================================================
if ck_check "step2b_done"; then
    log "[STEP2b] Already done, skipping"
    T_GPU_LTG=$(grep "GPU done:" $LOG_DIR/e2e_run.log | tail -1 | grep -oP '\d+')
else
    log "[STEP2b] latent_to_gene GPU"
    T1=$(date +%s)
    GSMAP_DEVICE=gpu gsmap run_latent_to_gene \
        --workdir $GPU_WORKDIR \
        --sample_name $SAMPLE \
        --annotation $ANNOT \
        --latent_representation latent_GVAE \
        --homolog_file $RES/homologs/mouse_human_homologs.txt 2>&1 | tee -a $LOG_DIR/e2e_run.log
    T2=$(date +%s)
    T_GPU_LTG=$((T2-T1))
    log "[STEP2b] GPU done: ${T_GPU_LTG}s"
    ck_done "step2b_done"
fi

# ============================================================
# STEP2 compare: feather marker scores precision
# ============================================================
if ck_check "step2_compare_done"; then
    log "[STEP2-COMPARE] Already done, skipping"
else
    log "[STEP2-COMPARE] Comparing CPU vs GPU feather outputs"
    CPU_FEATHER=$CPU_WORKDIR/$SAMPLE/latent_to_gene/${SAMPLE}_gene_marker_score.feather
    GPU_FEATHER=$GPU_WORKDIR/$SAMPLE/latent_to_gene/${SAMPLE}_gene_marker_score.feather

    python3 << PYEOF | tee -a $LOG_DIR/e2e_run.log
import pandas as pd
import numpy as np

cpu = pd.read_feather("$CPU_FEATHER").set_index("HUMAN_GENE_SYM")
gpu = pd.read_feather("$GPU_FEATHER").set_index("HUMAN_GENE_SYM")
common_genes = cpu.index.intersection(gpu.index)
common_cells = cpu.columns.intersection(gpu.columns)

cpu_m = cpu.loc[common_genes, common_cells].values.astype(np.float64)
gpu_m = gpu.loc[common_genes, common_cells].values.astype(np.float64)
fc, fg = cpu_m.flatten(), gpu_m.flatten()
nz = (fc != 0) | (fg != 0)
fc_nz, fg_nz = fc[nz], fg[nz]

corr = np.corrcoef(fc_nz, fg_nz)[0,1]
ad = np.abs(fc_nz - fg_nz)
print(f"  Genes: {len(common_genes):,}, Cells: {len(common_cells):,}")
print(f"  Non-zero: {nz.sum():,}/{len(fc):,} ({nz.mean()*100:.1f}%)")
print(f"  Pearson:          {corr:.8f}")
print(f"  Max diff:         {ad.max():.6e}")
print(f"  Mean diff:        {ad.mean():.6e}")
print(f"  <1e-3 match:      {(ad < 1e-3).mean()*100:.1f}%")
verdict = "PASS" if corr > 0.9999 and ad.max() < 0.1 else "WARN" if corr > 0.999 else "FAIL"
print(f"  Verdict:          {verdict}")
print(f"  Speedup (ltg):    ${T_CPU_LTG}/${T_GPU_LTG} = {${T_CPU_LTG}/${T_GPU_LTG}:.1f}x")
PYEOF
    ck_done "step2_compare_done"
fi

# ============================================================
# STEP3-5: ldscore, spatial_ldsc, cauchy (CPU and GPU)
# ============================================================
BFILE=$RES/LD_Reference_Panel/1000G_EUR_Phase3_plink/1000G.EUR.QC
KEEP_SNP=$RES/LDSC_resource/hapmap3_snps/hm
GTF=$RES/genome_annotation/gtf/gencode.v46lift37.basic.annotation.gtf
W_FILE=$RES/LDSC_resource/weights_hm3_no_hla/weights.

for mode in cpu gpu; do
    WDIR_VAR="${mode^^}_WORKDIR"
    WDIR="${!WDIR_VAR}"
    SUFFIX="${mode:0:1}"  # c or g

    # STEP3: generate_ldscore
    if ck_check "step3${SUFFIX}_done"; then
        log "[STEP3${SUFFIX}] ${mode^^} ldscore already done, skipping"
    else
        log "[STEP3${SUFFIX}] generate_ldscore ${mode^^}"
        T1=$(date +%s)
        gsmap run_generate_ldscore \
            --workdir $WDIR --sample_name $SAMPLE --chrom all \
            --bfile_root $BFILE --keep_snp_root $KEEP_SNP \
            --gtf_annotation_file $GTF --gene_window_size 50000 \
            --max_processes 16 2>&1 | tee -a $LOG_DIR/e2e_run.log
        T2=$(date +%s)
        log "[STEP3${SUFFIX}] ${mode^^} ldscore done: $((T2-T1))s"
        ck_done "step3${SUFFIX}_done"
    fi

    # STEP4: spatial_ldsc
    if ck_check "step4${SUFFIX}_done"; then
        log "[STEP4${SUFFIX}] ${mode^^} spatial_ldsc already done, skipping"
    else
        log "[STEP4${SUFFIX}] spatial_ldsc ${mode^^}"
        T1=$(date +%s)
        gsmap run_spatial_ldsc \
            --workdir $WDIR --sample_name $SAMPLE --trait_name $TRAIT \
            --sumstats_file $SUMSTATS --w_file $W_FILE \
            --num_processes 16 2>&1 | tee -a $LOG_DIR/e2e_run.log
        T2=$(date +%s)
        log "[STEP4${SUFFIX}] ${mode^^} spatial_ldsc done: $((T2-T1))s"
        ck_done "step4${SUFFIX}_done"
    fi

    # STEP5: cauchy_combination
    if ck_check "step5${SUFFIX}_done"; then
        log "[STEP5${SUFFIX}] ${mode^^} cauchy already done, skipping"
    else
        log "[STEP5${SUFFIX}] cauchy_combination ${mode^^}"
        gsmap run_cauchy_combination \
            --workdir $WDIR --sample_name $SAMPLE --trait_name $TRAIT \
            --annotation $ANNOT 2>&1 | tee -a $LOG_DIR/e2e_run.log
        log "[STEP5${SUFFIX}] ${mode^^} cauchy done"
        ck_done "step5${SUFFIX}_done"
    fi
done

# ============================================================
# STEP6: Final comparison (spatial_ldsc + cauchy)
# ============================================================
log "[STEP6] Final comparison: spatial_ldsc + cauchy"
python3 << 'PYEOF' | tee -a $LOG_DIR/e2e_run.log
import pandas as pd
import numpy as np
from pathlib import Path

cpu_base = Path("$CPU_WORKDIR/$SAMPLE")
gpu_base = Path("$GPU_WORKDIR/$SAMPLE")
trait = "$TRAIT"

# spatial_ldsc comparison
ldsc_cpu_dir = cpu_base / "spatial_ldsc" / trait
ldsc_gpu_dir = gpu_base / "spatial_ldsc" / trait
print("\n=== spatial_ldsc comparison ===")
if ldsc_cpu_dir.exists() and ldsc_gpu_dir.exists():
    cpu_files = sorted(ldsc_cpu_dir.glob("*.csv.gz"))
    gpu_files = sorted(ldsc_gpu_dir.glob("*.csv.gz"))
    if cpu_files and gpu_files:
        cpu_ldsc = pd.read_csv(cpu_files[0])
        gpu_ldsc = pd.read_csv(gpu_files[0])
        print(f"Shape: CPU={cpu_ldsc.shape}, GPU={gpu_ldsc.shape}")
        for col in ["slope", "slope_se", "pvalue"]:
            if col in cpu_ldsc.columns and col in gpu_ldsc.columns:
                c = cpu_ldsc[col].values.astype(float)
                g = gpu_ldsc[col].values.astype(float)
                valid = np.isfinite(c) & np.isfinite(g)
                if valid.sum() > 1:
                    corr = np.corrcoef(c[valid], g[valid])[0,1]
                    mae = np.abs(c[valid] - g[valid]).mean()
                    print(f"  {col:12s}: Pearson={corr:.8f}, MAE={mae:.4e}")

# cauchy_combination comparison
cauchy_cpu_dir = cpu_base / "cauchy_combination"
cauchy_gpu_dir = gpu_base / "cauchy_combination"
print("\n=== cauchy_combination comparison ===")
if cauchy_cpu_dir.exists() and cauchy_gpu_dir.exists():
    cpu_files = sorted(cauchy_cpu_dir.glob("*.csv"))
    gpu_files = sorted(cauchy_gpu_dir.glob("*.csv"))
    if cpu_files and gpu_files:
        cpu_c = pd.read_csv(cpu_files[0])
        gpu_c = pd.read_csv(gpu_files[0])
        print(f"Shape: CPU={cpu_c.shape}, GPU={gpu_c.shape}")
        for col in cpu_c.select_dtypes("number").columns[:5]:
            if col in gpu_c.columns:
                c = cpu_c[col].values.astype(float)
                g = gpu_c[col].values.astype(float)
                valid = np.isfinite(c) & np.isfinite(g)
                if valid.sum() > 1:
                    corr = np.corrcoef(c[valid], g[valid])[0,1]
                    mae = np.abs(c[valid] - g[valid]).mean()
                    print(f"  {col:12s}: Pearson={corr:.8f}, MAE={mae:.4e}")
PYEOF

log "[STEP6] ALL DONE"
log "========== Pipeline Complete: $(date) =========="
