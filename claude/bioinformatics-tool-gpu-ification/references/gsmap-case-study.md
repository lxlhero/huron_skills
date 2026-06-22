# gsMap GPU-ification Case Study

## Tool info
- Name: gsMap
- Paper: Song L et al. Nature (2025)
- Repo: https://github.com/JianYang-Lab/gsMap
- Language: Python 3.10+, PyTorch 2.3+, PyG 2.3+
- License: MIT

## Algorithm
1. GNN training: GAT autoencoder on spatial transcriptomics data (300 epochs)
2. GSS computation: per-spot cosine_similarity + gmean over microdomain neighbors
3. S-LDSC + Cauchy combination: LD score regression per spot, aggregated for spatial region significance

## Hotspot
GSS computation (latent_to_gene.py, run_latent_to_gene function, lines 282-298):
- Per-cell rankdata loop: n_cells x n_genes
- Per-spot marker score loop: n_cells iterations calling cosine_similarity + gmean

## GPU Strategy
- Rank: KEEP on CPU. scipy.rankdata is highly optimized C; GPU torch_rankdata is 20x slower due to per-row Python tie-handling loops.
- Marker scores: VECTORIZED on GPU. F.cosine_similarity(query.unsqueeze(1), keys[neighbors], dim=2) replaces N individual CUDA calls with one. torch.log-mean replaces scipy.stats.gmean.

## Benchmark Results (H200, 10K spots x 2K genes)
- CPU total: 5.4s (rank 1.4s + marker 4.0s)
- GPU hybrid: 1.7s (rank CPU 1.4s + marker GPU 0.16s)
- Overall speedup: 3.1x
- Marker step speedup: 29x
- Cosine sub-step: from 360ms (per-spot loop) to 0.5ms (vectorized) = 690x
- Max numerical diff: 4.29e-06
- Pearson r: 1.000000

## Key File
tools/gsMap/src/latent_to_gene_gpu.py (~300 lines, drop-in replacement for original latent_to_gene.py)
- compute_marker_scores_gpu(): new function, heart of GPU acceleration
- Dual path: no annotations -> GPU vectorized fast path; with annotations -> CPU fallback
- Integration: replace original run_latent_to_gene() with this version
