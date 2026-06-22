# Benchmark Data Sources for GPU Validation

User prefers real benchmark data over synthetic. Synthetic data is for dev-phase correctness checks only; formal reports to leadership require real data.

## gsMap (spatial transcriptomics)

**No standalone benchmark dataset exists.** The official tutorial data is packaged for the full pipeline.

1. Official tutorial data (Yanglab server):
   - `gsMap_resource.tar.gz` — 651MB: LD panels, gene annotations, enhancer maps
   - `gsMap_example_data.tar.gz` — 2.37GB: E16.5_E1S1.MOSTA.h5ad + GWAS summary stats (IQ, Height, MCHC)
   - URL: https://yanglab.westlake.edu.cn/data/gsMap/
   - ACCESSIBILITY: Reachable from Mac (slow ~200-400KB/s, expect 2-3 hours for 3GB total). NOT reachable from PJLab dev machine (HTTP 000 timeout). Download locally on Mac, then transfer to shared storage.
   - Use `curl -C - -L -o FILE URL` for resumeable downloads — server is flaky and may drop connections.
   - After transfer to shared storage, DELETE local copies — Mac SSD space is tight (user explicit directive).

2. Zenodo (10.5281/zenodo.14744887): Code only, no data.

3. Paper datasets (public, but need full preprocessing):
   - Mouse embryo Stereo-seq (Chen et al. 2022, Cell)
   - Human embryo CS8 ST data
   - Macaque cortical Stereo-seq
   - GWAS summary stats from public consortia

4. Fallback: 10x Genomics public Visium datasets + public GWAS stats.
   - Mouse brain Visium: https://www.10xgenomics.com/datasets
   - GWAS: OpenGWAS / EBI GWAS Catalog
   - Requires running gsMap's full GNN pipeline to generate latent representations

### Data Transfer Workflow (Mac → Shared Storage)

Since Mac cannot mount GPFS directly, pipe through the dev machine:

```
# Transfer
cat LOCAL_FILE | ssh dev-machine "cat > /mnt/shared-storage-user/liangxiuliang/FILE"

# Verify
ssh dev-machine "ls -la /mnt/shared-storage-user/liangxiuliang/FILE"

# Delete local
rm LOCAL_FILE
```

Always delete local copies after successful transfer. Files on shared storage are readable from H200 pods despite root ownership (verified: root squash does NOT block reads, only execution/writes may be restricted).

### gsMap Pod Execution Quirks

- CLI command is `python3 -m gsMap`, NOT `gsmap` — the `gsmap` binary may not be in PATH inside the Docker image (confirmed on `gsmap-gpu:v1.0`). All subcommands work: `python3 -m gsMap run_latent_to_gene`, etc.
- GNN training (`run_find_latent_representations`) needs ~60GB RAM and writes latent_GVAE to `{workdir}/{sample_name}/{sample_name}.h5ad`
- **For GPU benchmark: skip GNN training entirely.** The `latent_to_gene` step only needs `obsm['latent_GVAE']` — inject PCA-initialized latents instead. The computation is identical regardless of latent source. This saves 30–60 minutes and tests the right thing (inference, not training).
- Benchmark compares feather files output by CPU vs GPU `run_latent_to_gene`. Key metrics: Pearson correlation (target >0.9999), max absolute diff (target <1e-4), speedup ratio.

### rjob Submission Template

```bash
# From dev machine with kubebrain env sourced:
rjob submit \
  --task-type=idle \
  --name=gsmap-bench \
  --enable-sshd \
  --gpu=1 \
  --memory=100000 \
  --cpu=16 \
  --mount=gpfs://gpfs1/liangxiuliang:/mnt/shared-storage-user/liangxiuliang \
  --image=registry.h.pjlab.org.cn/ailab-sdpdev-sdpdev_gpu/gsmap-gpu:v1.0 \
  -P 1 \
  -- bash -c "sleep 86400"
```

Note: `-r=restartjobonfailure` may not be recognized — check rjob version. Pod auto-restart on failure is separate from rjob flags.

## susieR (fine-mapping)

suSIE is a method, not a data-bound tool. Benchmark data is defined by matrix dimensions (N×P×L).

1. User's own fine-mapping data (ideal, but may not be available)
2. Public GWAS fine-mapping examples:
   - UK Biobank fine-mapping results (various traits)
   - GTEx eQTL fine-mapping data
3. Synthetic data is acceptable for correctness validation (what we used)

## SCAVENGE (single-cell trait association)

1. Tutorial data from SCAVENGE docs: requires scATAC-seq or scRNA-seq + GWAS
2. Paper data: hematopoietic scATAC-seq (Buenrostro lab) + GWAS traits
3. Public 10x single-cell datasets + public GWAS

## Priority Order for Data Sourcing

1. Official tutorial/example data (packaged, ready to use)
2. Public standard datasets (10x, GEO, GWAS Catalog)
3. Paper supplementary data
4. Synthetic (dev-phase correctness check only)
