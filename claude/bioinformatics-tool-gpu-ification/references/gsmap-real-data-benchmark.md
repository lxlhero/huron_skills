# gsMap Real-Data Benchmark Recipe

## Official Data Source

Yanglab server (slow but accessible from PJLab network):
```
https://yanglab.westlake.edu.cn/data/gsMap/gsMap_resource.tar.gz       (651 MB)
https://yanglab.westlake.edu.cn/data/gsMap/gsMap_example_data.tar.gz   (2.37 GB)
```

`gsMap_resource.tar.gz` contains:
- `LD_Reference_Panel/` — 1000G EUR Phase3 PLINK files
- `LDSC_resource/` — HapMap3 SNPs, LDSC weights
- `genome_annotation/` — GTF + enhancer annotations
- `homologs/` — mouse/cacaque human gene mapping
- `quick_mode/` — pre-built SNP-gene weight matrix

`gsMap_example_data.tar.gz` contains:
- `ST/E16.5_E1S1.MOSTA.h5ad` — 121,767 cells × 28,204 genes (mouse embryo, MOSTA technology)
- `ST/E16.5_E2S11.MOSTA.h5ad` — second replicate
- `GWAS/` — IQ, Height, SCZ summary statistics

## Benchmark Approach (Skip GNN Training)

Key insight: `latent_to_gene` is a pure statistical computation. It only needs `latent_GVAE` (32-dim vectors) in `adata.obsm` — the origin of these vectors doesn't matter. GNN training takes 30-60 minutes and is irrelevant to the GPU benchmark.

```python
# Inject synthetic latent representations (PCA + noise, simulates GVAE output)
from sklearn.decomposition import PCA
X_log = np.log1p(adata.X.toarray().astype(np.float64))
pca = PCA(n_components=32, random_state=seed)
latent = pca.fit_transform(X_log) + rng.normal(0, 0.05, (n_cells, 32))
adata.obsm['latent_GVAE'] = latent.astype(np.float32)
```

## GPU Path Control

The GPU module has two paths controlled by `config.annotation`:
- `annotation=None` → GPU vectorized fast path (gene-chunked for large data)
- `annotation='annotation'` → CPU per-spot fallback (annotation filtering is irregular)

For maximum GPU benchmark speedup, pass `annotation=None`.

## Gene Chunking for Large Datasets

For datasets like 121K cells × 28K genes, the native GPU path OOMs because
`ranks[neighbors]` creates a (N, K, G) = (121767, 201, 28204) tensor ≈ 2.7 TB.

```python
free_vram = total_vram - allocated
chunk_size = max(100, int(free_vram * 0.5 / (n_cells * K * 4)))
for g_chunk in range(0, n_genes, chunk_size):
    ranks_chunk = ranks[:, gs:ge].to(device)
    neigh_ranks = ranks_chunk[neigh_idx]  # only (N, K, chunk)
    # ... compute for this chunk ...
    del ranks_chunk, neigh_ranks  # free VRAM between chunks
```

## Data Transfer Pattern (Mac → Dev Machine → Shared Storage)

```bash
# Pipe through dev machine to shared storage
cat local_file.tar.gz | ssh dev_machine "cat > /mnt/shared-storage/path/file.tar.gz"

# Extract on POD (not dev machine) to avoid root squash issues
ssh pod "tar -xzf /mnt/shared-storage/path/file.tar.gz -C /mnt/shared-storage/path/"

# Delete local immediately
rm local_file.tar.gz
```

## gsMap CLI in Docker

The `gsmap` console script may not exist in pip-installed gsMap. Always use:
```bash
python3 -m gsMap run_find_latent_representations ...
python3 -m gsMap run_latent_to_gene ...
```

## Output Comparison

Both CPU and GPU save results as `.feather` files at:
`{workdir}/{sample_name}/latent_to_gene/{sample_name}_gene_marker_score.feather`

Matrix shape after homolog mapping + MT gene removal: ~16,331 genes × 121,767 cells.
Expected: Pearson r = 1.0, max diff = 0 (when using same algorithm on GPU vs CPU).
