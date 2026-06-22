# SCAVENGE GPU-ification Case Study

## Tool info
- Name: SCAVENGE
- Author: Fulong Yu (Broad Institute, Sankaran Lab)
- Repo: https://github.com/sankaranlab/SCAVENGE
- Language: R
- License: GPL (>= 2)
- Version: 1.0.2

## Algorithm
1. LSI dimensionality reduction (do_lsi): scATAC peak matrix -> latent space
2. Graph construction (getmutualknn): RANN::nn2 KNN -> mutual KNN -> sparse adjacency
3. Propagation + test (randomWalk_sparse + get_sigcell_simple):
   - Column-normalize: intM = t(t(intM)/colSums(intM))
   - Random walk: p_{t+1} = (1-gamma)*W %*% p_t + gamma*p0
   - Permutation test: 1000 random seed sets -> 1000 propagations -> z-score

## Hotspot
get_sigcell_simple calls randomWalk_sparse 1000x for permutation testing.
Each call is O(|E| * iterations) CSR SpMV.

## GPU Strategy
- Graph: scipy CSR -> torch.sparse_csr, loaded once on GPU
- Propagation: batch all 1000 permutations as columns of P0 matrix
- One torch.sparse.mm(W, P) call replaces 1000 serial CSR dot operations

## Benchmark Results (H200)
- 5K cells, 300K edges, 100 traits batch: CPU 0.68s -> GPU 0.07s (9.3x)
- 20K cells: CPU 0.35s -> GPU 0.03s (12.9x)
- Real-world (1000 permutations, 5K cells): CPU ~7s -> GPU ~0.07s (~100x)
- Max numerical diff: 5.04e-09

## Algorithm Match Verification
GPU code exactly replicates R randomWalk_sparse (line 53-70 of randomWalk_sparse.R):
- Same column normalization: W = W / colSums(W)
- Same iteration: p_new = (1-gamma) * W.T @ p + gamma * p0
- Same convergence: sum(|p_new - p|) < cutoff

## Key File
tools/SCAVENGE/src/scavenge_gpu.py (~150 lines)
- propagate_batch_gpu(): batched multi-trait propagation
- csr_to_torch_sparse(): scipy CSR -> torch sparse CSR converter

## Pitfalls
- torch.sparse.mv() does NOT exist in PyTorch 2.3.1; use torch.mv()
- scipy CSR multiply() returns COO; must call .tocsr() after normalization
- Single-trait propagation is break-even; batching is the multiplier
