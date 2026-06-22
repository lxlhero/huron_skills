# spatial_ldsc GPU 加速 — 方法记录

状态：2026-06-11，精度已验证（beta Pearson=0.99993），全量速度测试中。

## 关键发现：half-weight 陷阱

**问题**：CPU版 get_weight_optimized 返回 sqrt(raw_w)，通过预乘设计矩阵实现 WLS：
```python
# CPU: pre-multiply X and y by sqrt(weight)
w_half = get_weight_optimized(...)  # returns sqrt(raw_w)
x_focal = X * w_half[:, None]
y_w = y * w_half[:, None]
beta = lstsq(x_focal, y_w)
# Effective WLS weight = w_half^2 = raw_w
```

GPU版如果直接使用 w_half 作为 WLS 权重而不平方，有效权重是 w_half 而非 w_half^2，
导致 beta 精度从 0.9999 降到 0.90。

**修复**：GPU代码内部对输入权重做平方：`W = weights ** 2`
修复后 beta: Pearson=0.99993, MAE=2.90e-12 (200 spot)

## 算法：block matrix Sherman-Morrison

对每个 spot (共 N 个)，设计矩阵 X_i = [spatial_col_i, X_shared_base] (M, K+1)

系统矩阵 A_i = X_i^T diag(w_i) X_i，按块组装避免 N 份 (M,K+1) 展开：

```
A_i = [[a_i,  c_i^T],     a_i = spatial_col_i^T diag(w_i) spatial_col_i  (标量)
       [c_i,  B_i   ]]    c_i = Xb^T (w_i ⊙ spatial_col_i)              (K维向量)
                           B_i = Xb^T diag(w_i) Xb                       (K×K矩阵)
```

所有 N 个 (K+1,K+1) 矩阵通过一次 batched torch.linalg.inv 求逆。

## Jackknife vs Sandwich SE

- CPU 用 jackknife 估计标准误
- GPU 用 sandwich (HC0) estimator
- beta 点估计应完全一致（已验证）
- se 差异是方法差异，不是 bug
