# gsMap E2E Resume from Checkpoint

When an E2E pipeline fails at STEP 3 (or later) after STEP 1+2 completed successfully,
resume instead of restarting. This saves 17+ minutes per fix cycle.

## Checkpoint outputs (must exist on GPFS)

After STEP 1: `{workdir}/{sample}/find_latent_representations/{sample}_add_latent.h5ad`
After STEP 2: `{workdir}/{sample}/latent_to_gene/{sample}_gene_marker_score.feather`

## Resume script template

```bash
#!/bin/bash
set -e -o pipefail
export PATH=/opt/conda/bin:$PATH

DATA=/mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap
RES=/mnt/shared-storage-gpfs2/liangxiuliang-2/gsMap_resource
SAMPLE=E16.5_E1S1.MOSTA
ANNOT=annotation
TRAIT=IQ
CPU_WD=$DATA/workdir_cpu_v181
RESULT=$CPU_WD/e2e_result.txt

# Verify STEP 1+2 outputs
LATENT=$CPU_WD/$SAMPLE/find_latent_representations/${SAMPLE}_add_latent.h5ad
MARKER=$CPU_WD/$SAMPLE/latent_to_gene/${SAMPLE}_gene_marker_score.feather
[ -f "$LATENT" ] || { echo "MISSING: $LATENT"; exit 1; }
[ -f "$MARKER" ] || { echo "MISSING: $MARKER"; exit 1; }

log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a $RESULT; }

# STEP 3: generate_ldscore
log "=== STEP 3: generate_ldscore ==="
gsmap run_generate_ldscore \
    --workdir $CPU_WD --sample_name $SAMPLE \
    --chrom all --bfile_root $RES/LD_Reference_Panel/1000G_EUR_Phase3_plink/1000G.EUR.QC \
    --keep_snp_root $RES/LDSC_resource/hapmap3_snps/hm \
    --gtf_annotation_file $RES/genome_annotation/gtf/gencode.v46lift37.basic.annotation.gtf \
    --gene_window_size 50000 2>&1 | tee -a $RESULT

# STEP 4: spatial_ldsc
log "=== STEP 4: spatial_ldsc ==="
GSMAP_DEVICE=cpu gsmap run_spatial_ldsc \
    --workdir $CPU_WD --sample_name $SAMPLE \
    --trait_name $TRAIT --sumstats_file $DATA/gsMap_example_data/GWAS/IQ_NG_2018.sumstats.gz \
    --w_file $RES/LDSC_resource/weights_hm3_no_hla/weights. \
    --num_processes 16 2>&1 | tee -a $RESULT

# STEP 5: cauchy_combination
log "=== STEP 5: cauchy_combination ==="
gsmap run_cauchy_combination \
    --workdir $CPU_WD --sample_name $SAMPLE \
    --trait_name $TRAIT --annotation $ANNOT 2>&1 | tee -a $RESULT

log "DONE"
```

## Deployment

1. Upload to GPFS: `cat resume.sh | ssh <bastion> 'cat > /mnt/...gtpf2/.../gsmap/e2e_cpu_resume.sh'`
2. Submit: `rjob submit ... -- bash /mnt/.../gsmap/e2e_cpu_resume.sh`

## Key rules

- Do NOT clean workdir before resuming (this deletes STEP 1+2 outputs)
- Verify checkpoint files exist before proceeding
- Use same workdir name as the original run (STEP 3+ write alongside existing STEP 1+2 outputs)
- For GPU resume: GPU STEP 2 produces different latent-to-gene outputs than CPU STEP 2, so CPU workdir can't be reused for GPU STEP 3+. Need a prior GPU run that completed STEP 2.
