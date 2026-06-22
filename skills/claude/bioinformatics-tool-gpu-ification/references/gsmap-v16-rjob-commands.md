# gsMap v1.6 E2E rjob 命令模板

## 镜像
```
registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.6
```

## 数据路径
```
BASE=/mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap
DATA=$BASE/gsMap_example_data
RES=/mnt/shared-storage-gpfs2/liangxiuliang-2/gsMap_resource
H5AD=$DATA/ST/E16.5_E1S1.MOSTA.h5ad
SUMSTATS=$DATA/GWAS/IQ_NG_2018.sumstats.gz
BFILE=$RES/LD_Reference_Panel/1000G_EUR_Phase3_plink/1000G.EUR.QC
KEEP_SNP=$RES/LDSC_resource/hapmap3_snps/hm
GTF=$RES/genome_annotation/gtf/gencode.v46lift37.basic.annotation.gtf
W_FILE=$RES/LDSC_resource/weights_hm3_no_hla/weights.
HOMOLOG=$RES/homologs/mouse_human_homologs.txt
```

## rjob 提交（零变量展开，全路径写死）

外层必须用单引号包裹整个 bash -c 参数，防止本地 shell 展开 $。

### CPU E2E（16核 120GB）
```bash
rjob submit \
  --name gsmap-cpu-e2e \
  --task-type idle \
  --enable-sshd \
  --image registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.6 \
  --cpu 16 \
  --memory 122880 \
  -- bash -c '
export PATH=/opt/conda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/cuda/lib64:$LD_LIBRARY_PATH

WORKDIR=/mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/workdir_cpu

# STEP3: generate_ldscore (CPU, ~66min)
gsmap run_generate_ldscore \
  --workdir /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/workdir_cpu \
  --sample_name E16.5_E1S1.MOSTA \
  --chrom all \
  --bfile_root /mnt/shared-storage-gpfs2/liangxiuliang-2/gsMap_resource/LD_Reference_Panel/1000G_EUR_Phase3_plink/1000G.EUR.QC \
  --keep_snp_root /mnt/shared-storage-gpfs2/liangxiuliang-2/gsMap_resource/LDSC_resource/hapmap3_snps/hm \
  --gtf_annotation_file /mnt/shared-storage-gpfs2/liangxiuliang-2/gsMap_resource/genome_annotation/gtf/gencode.v46lift37.basic.annotation.gtf \
  --gene_window_size 50000 && \

# STEP4: spatial_ldsc (CPU, ~3min)
gsmap run_spatial_ldsc \
  --workdir /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/workdir_cpu \
  --sample_name E16.5_E1S1.MOSTA \
  --trait_name IQ \
  --sumstats_file /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/gsMap_example_data/GWAS/IQ_NG_2018.sumstats.gz \
  --w_file /mnt/shared-storage-gpfs2/liangxiuliang-2/gsMap_resource/LDSC_resource/weights_hm3_no_hla/weights. \
  --num_processes 16 && \

# STEP5: cauchy_combination (CPU, ~7min)
gsmap run_cauchy_combination \
  --workdir /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/workdir_cpu \
  --sample_name E16.5_E1S1.MOSTA \
  --trait_name IQ \
  --annotation annotation
'
```

### GPU E2E（1×H200 120GB）
```bash
rjob submit \
  --name gsmap-gpu-e2e \
  --task-type idle \
  --enable-sshd \
  --image registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.6 \
  --gpu 1 \
  --memory 122880 \
  -- bash -c '
export PATH=/opt/conda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/cuda/lib64:$LD_LIBRARY_PATH
export GSMAP_DEVICE=gpu

WORKDIR=/mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/workdir_gpu

# STEP3: generate_ldscore (CPU — 不设 GSMAP_DEVICE, ~61min)
gsmap run_generate_ldscore \
  --workdir /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/workdir_gpu \
  --sample_name E16.5_E1S1.MOSTA \
  --chrom all \
  --bfile_root /mnt/shared-storage-gpfs2/liangxiuliang-2/gsMap_resource/LD_Reference_Panel/1000G_EUR_Phase3_plink/1000G.EUR.QC \
  --keep_snp_root /mnt/shared-storage-gpfs2/liangxiuliang-2/gsMap_resource/LDSC_resource/hapmap3_snps/hm \
  --gtf_annotation_file /mnt/shared-storage-gpfs2/liangxiuliang-2/gsMap_resource/genome_annotation/gtf/gencode.v46lift37.basic.annotation.gtf \
  --gene_window_size 50000 && \

# STEP4: spatial_ldsc (GPU, ~2min)
GSMAP_DEVICE=gpu gsmap run_spatial_ldsc \
  --workdir /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/workdir_gpu \
  --sample_name E16.5_E1S1.MOSTA \
  --trait_name IQ \
  --sumstats_file /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/gsMap_example_data/GWAS/IQ_NG_2018.sumstats.gz \
  --w_file /mnt/shared-storage-gpfs2/liangxiuliang-2/gsMap_resource/LDSC_resource/weights_hm3_no_hla/weights. \
  --num_processes 16 && \

# STEP5: cauchy_combination (CPU, ~4min)
gsmap run_cauchy_combination \
  --workdir /mnt/shared-storage-gpfs2/liangxiuliang-2/gsmap/workdir_gpu \
  --sample_name E16.5_E1S1.MOSTA \
  --trait_name IQ \
  --annotation annotation
'
```

## 要点

1. 外层用单引号 `'...'` 包裹命令，防止本地 shell 展开 `$`
2. 全路径写死，零变量引用，避免作用域问题
3. STEP3 generate_ldscore 即使在 GPU job 中也不设 GSMAP_DEVICE=gpu（走 CPU，I/O 密集无加速）
4. `&&` 串联：任一步失败即停
5. rjob 语法：`--task-type idle`（不是 `--mode idle`），`--memory` 单位 MiB
6. workdir_gpu 和 workdir_cpu 必须用不同目录（隔离中间产物）
7. 每个 workdir ~200GB，GPFS 配额 512GB，E2E 后必删一个
8. Bastion SSH 必须用 `ailab-ma4agismall.ws` 后缀才能访问 GPFS workdir
