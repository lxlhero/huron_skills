---
name: c550-k8s-inference
description: K8s 直接推理 C550 — kubectl exec 进 Pod 跑推理、上传文件、下载结果、监控 GPU
category: mlops
---

# K8s 直接推理 C550（沐曦 MetaX）

绕过 REST API 网关，通过 kubectl exec 直接在 C550 Pod 内运行科学模型推理。适用于 REST API 未覆盖的模型、自定义数据集、批量推理等场景。

## 一、前置信息

| 项目 | 值 |
|------|-----|
| KUBECONFIG | /Users/huron/code/ai_lab/kubeconfig_dir/config-vc-c550-ai4s-sys |
| 命名空间 | studio-ams |
| GPU | MetaX C550 (MACA 3.3.0, 64GB VRAM) |
| PVC | afs-inference-shared (80Ti, RWX, 挂载于 /data/) |
| GPU 资源名 | metax-tech.com/gpu |

**⚠️ 铁律：不要删除或修改已有资源。** C550 是共享集群，只操作自己创建的资源。

## 二、环境变量

```bash
export KUBECONFIG=/Users/huron/code/ai_lab/kubeconfig_dir/config-vc-c550-ai4s-sys
```

所有 kubectl 命令默认操作 studio-ams 命名空间。

**⚠️ GPU 节点查询避免超时**：24 节点集群，`kubectl describe nodes` 会超时（25s+）。用 jsonpath：

```bash
# GPU 节点清单
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.capacity.metax-tech\.com/gpu}{"\t"}{.status.allocatable.metax-tech\.com/gpu}{"\n"}{end}' | grep -v "^.*\t\t$"

# 总 GPU
kubectl get nodes -o jsonpath='{range .items[*]}{.status.allocatable.metax-tech\.com/gpu}{"\n"}{end}' | grep -v '^$' | awk '{sum+=$1} END {print sum}'
```

## 三、查找 Pod

### 模型 Pod 名规律

| 模型 | Pod 名 pattern | 容器名 |
|------|---------------|--------|
| alphafold3 | `alphafold3-1-*` | alphafold3-main |
| boltzgen | `boltzgen-1-*` | — |
| rfdiffusion | `rfdiffusion-1-*` | — |
| mattersim | `mattersim-*` | — |
| mace | `mace-*` | — |
| evo2 | `evo2-*` | — |
| esm2 | `openfold-esm-protenix-mmseqs2-*` | — |

```bash
# 列出某模型所有 pod
kubectl get pods -n studio-ams | grep <keyword>

# 取第一个 running pod
POD=$(kubectl get pods -n studio-ams | grep <keyword> | awk 'NR==1{print $1}')
```

**⚠️ 多容器 Pod**：部分 Pod 有多容器，`kubectl exec` 默认进第一个。指定容器：`-c <container_name>`。

## 四、文件上传

### 推荐：tar pipe（大文件/多文件）

`kubectl cp` 对大文件及多个文件偶发静默失败。优先用 tar pipe：

```bash
# 上传目录
tar cf - * | kubectl exec -n studio-ams -i $POD -- tar xf - -C /tmp/inputs/

# 上传单个文件
cat file.json | kubectl exec -n studio-ams -i $POD -- tee /tmp/inputs/file.json > /dev/null

# 验证
kubectl exec -n studio-ams $POD -- ls -la /tmp/inputs/
kubectl exec -n studio-ams $POD -- wc -l /tmp/inputs/*
```

### 备选：kubectl cp

```bash
kubectl cp <local_file> studio-ams/$POD:/target/path -c <container>
```

**⚠️ 大文件优先 tar 后上传再解压**（避免 kubectl cp 超时）：
```bash
tar czf - inputs/ | kubectl exec -i studio-ams/$POD -- tar xzf - -C /data/
```

**⚠️ gzip 压缩的 tar 可能在上传大文件时截断**（管道缓冲区问题）。建议用未压缩 tar pipe，或上传后验证文件大小与本地一致。

## 五、运行推理

### 5.1 单任务直接执行

```bash
kubectl exec -n studio-ams $POD -- python3 /path/to/script.py --in input --out /tmp/out
```

### 5.2 批量推理（推荐 nohup 后台）

```bash
# 1. 上传批量脚本
kubectl cp run_batch.py studio-ams/$POD:/tmp/run_batch.py

# 2. 后台启动（nohup，断开 shell 后进程继续）
kubectl exec -n studio-ams $POD -- bash -c \
  'cd /tmp && nohup python3 run_batch.py > batch.log 2>&1 & echo $!'

# 3. 监控
kubectl exec -n studio-ams $POD -- tail -20 /tmp/batch.log
```

**⚠️ 不能用 `kubectl exec ... nohup ... &` 在本地交互式 shell 启动**：进程随 exec 会话退出而死亡。必须用 `bash -c '... &'` 内联。

### 5.3 通用批量脚本模板

```python
#!/usr/bin/env python3
"""通用批量推理脚本：遍历输入、skip 已完成、nohup 后台运行"""
import subprocess, os, sys, glob

INPUT_DIR = "/tmp/inputs"
OUTPUT_DIR = "/tmp/outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

for f in sorted(glob.glob(f"{INPUT_DIR}/*")):
    name = os.path.splitext(os.path.basename(f))[0]
    out = f"{OUTPUT_DIR}/{name}"
    
    # Skip if already done（根据模型输出格式判断）
    if os.path.exists(f"{out}/<done_marker>"):
        print(f"SKIP {name}: already done")
        continue
    
    print(f"[{name}] Running...")
    result = subprocess.run(
        ["<inference_cmd>", "--input", f, "--output", out],
        capture_output=True, text=True, timeout=3600
    )
    print(f"[{name}] exit={result.returncode}")
    sys.stdout.flush()

print("=== ALL DONE ===")
```

## 六、监控

### GPU 状态

```bash
# mx-smi（C550 专用，类 nvidia-smi）
kubectl exec -n studio-ams $POD -- mx-smi

# ⚠️ mx-smi 偶发进入 D 状态（不可中断睡眠），产生 <defunct> 僵尸
# 诊断用更轻量替代：
kubectl exec -n studio-ams $POD -- ps aux | grep python
```

### 进程监控

```bash
# 查看推理进程
kubectl exec -n studio-ams $POD -- ps aux | grep -E "python|run_"

# 查看 GPU 占用进程
kubectl exec -n studio-ams $POD -- bash -c 'ps aux | grep <model_cmd>'
```

### 日志查看

```bash
# 尾部
kubectl exec -n studio-ams $POD -- tail -20 /tmp/batch.log

# 实时看（需要 PTY）
kubectl exec -n studio-ams -it $POD -- tail -f /tmp/batch.log

# 统计完成数
kubectl exec -n studio-ams $POD -- grep -c '=> OK' /tmp/batch.log
```

### 输出统计

```bash
# 统计输出文件数
kubectl exec -n studio-ams $POD -- ls /tmp/outputs/ | wc -l

# 统计特定类型
kubectl exec -n studio-ams $POD -- find /tmp/outputs/ -name "*_model.cif" | wc -l
```

## 七、结果下载

```bash
# 1. Pod 内打包
kubectl exec -n studio-ams $POD -- tar czf /tmp/results.tar.gz -C /tmp/outputs .

# 2. 下载
kubectl cp studio-ams/$POD:/tmp/results.tar.gz ./results.tar.gz

# 3. 解压
tar xzf results.tar.gz -C ./muxi_results/
```

**⚠️ kubectl cp 静默失败**：下载大文件时不报错但实际未传。下载后验证文件大小：
```bash
ls -lh ./results.tar.gz
kubectl exec -n studio-ams $POD -- ls -lh /tmp/results.tar.gz  # 对比
```

### 增量备份

AF3 ABAG+PL 有专用的增量备份脚本，从 Pod 的 PVC 输出目录同步新完成的结果到本地：

```bash
# 脚本路径：infer_tasks/gpu_accuracy_comparison/alphafold3_abag_pl/backup_results.py
cd /Users/huron/code/ai_lab
python3 infer_tasks/gpu_accuracy_comparison/alphafold3_abag_pl/backup_results.py
```

原理：`kubectl exec` 进 Pod → `find` 新完成的 `_model.cif` → `tar` pipe 下载到本地 `results_c550/` 目录。支持断点续传（skip 已下载）。

## 八、PVC 共享存储

所有科学模型 Pod 挂载同一共享 PVC `afs-inference-shared`（80Ti, RWX），/data/ 内容完全一致。可在任一 Pod 创建输入、在任一 Pod 读取输出。

### AlphaFold3 PVC 路径

| 路径 | 内容 |
|------|------|
| /data/af3_abag_pl_inputs/ | 输入 JSON |
| /data/af3_abag_pl_outputs/ | 推理结果 CIF |
| /data/af3_abag_pl_batch.log | 批处理日志 |

### 通用 PVC 操作

```bash
# 在不同 Pod 创建目录
kubectl exec -n studio-ams <pod1> -- mkdir -p /data/my_task/inputs
kubectl exec -n studio-ams <pod2> -- ls /data/my_task/inputs  # 可见

# 注意：并行写同一文件可能冲突
```

## 九、Deployment 管理

### 查看部署

```bash
kubectl get deploy -n studio-ams | grep <model>
kubectl describe deploy <name> -n studio-ams
```

### 重启

```bash
# rollout restart（推荐：先建新 pod 再删旧）
kubectl rollout restart deploy/<name> -n studio-ams

# 等待就绪
kubectl get deploy/<name> -n studio-ams -o jsonpath='{.status.readyReplicas}'

# 不要用 kubectl delete pod（> OVN IP 冲突风险）
```

**⚠️ `kubectl set env` 会触发 rolling restart**：瞬间杀死全部运行中进程。需要设环境变量时直接 patch deployment YAML，等自然重启生效。

### 扩容

```bash
kubectl scale deploy <name> -n studio-ams --replicas=8
```

### 自定义 Deployment

创建 YAML 然后 apply：

```bash
kubectl apply -f my-deploy.yaml
```

**关键参数**：
- `tolerations`: 必须有 `metax-tech.com/gpu`
- `volumeMounts`: PVC `afs-inference-shared` → `/data`
- `MACA_MPS_MODE=1`（AF3 必设，防止 GPU 句柄泄漏）
- 批处理用 `while true` 守护循环

### AF3 部署模板

参考 YAML：`infer_tasks/gpu_accuracy_comparison/alphafold3_abag_pl/c550_batch_deploy.yaml`

关键设计：

```yaml
# while true 守护循环：batch 退出后自动重启，Deployment controller 保证 Pod 被驱逐后重新调度
command: ["bash", "-c"]
args:
  - |
    export MACA_MPS_MODE=1
    while true; do
      python3 /data/run_af3_batch_c550_abag_pl.py 2>&1 | tee -a /data/af3_abag_pl_batch.log
      echo "Batch exited, restarting in 60s..."
      sleep 60
    done
```

监控命令：
```bash
# 查看部署日志
kubectl logs -n studio-ams <pod> -c alphafold3-main --tail=50
# 查看批处理进度
kubectl exec -n studio-ams <pod> -c alphafold3-main -- tail -5 /data/af3_abag_pl_batch.log
# 统计输出
kubectl exec -n studio-ams <pod> -c alphafold3-main -- ls /data/af3_abag_pl_outputs/ | wc -l
# 统计完成
kubectl exec -n studio-ams <pod> -c alphafold3-main -- grep -c '=> OK' /data/af3_abag_pl_batch.log
```

## 十、AlphaFold3 C550 专用

### 推理命令

```bash
# 进入 Pod
kubectl exec -n studio-ams $POD -it -c alphafold3-main -- bash

# 推理
export MACA_MPS_MODE=1  # 必须！
timeout 7200 /opt/conda/envs/alphafold3/bin/python \
  /opt/alphafold3/run_alphafold.py \
  --json_path=/tmp/input.json \
  --output_dir=/tmp/out \
  --model_dir=/opt/weights \
  --norun_data_pipeline \
  --force_output_dir \
  --flash_attention_implementation=xla \
  --num_recycles=10 \
  --num_diffusion_samples=1 \
  --run_inference=true
```

### C550 特殊参数

| 参数 | 值 | 说明 |
|------|---|------|
| `MACA_MPS_MODE` | `1` | **必须设**，修复 Compute Queue type:21 句柄泄漏 |
| `flash_attention_implementation` | `xla` | C550 上推荐 xla |
| `MAX_SEQ_LEN` | `2000` | C550 硬限制（64GB VRAM），超过送 H200 |
| `TASK_TIMEOUT` | `7200` | 大蛋白 1000aa+ 需 30-110min |

### 超时与静默失败

- **热池首次运行**：XLA JIT 编译 300-725s，600s 以下大概率超时
- **静默失败模式**：日志显示 5 seed 通过 featurisation 但无 model inference 输出 → 超时，非 GPU 故障
- **空 CIF 陷阱**：AF3 崩溃时先写空文件后退出，`is_done()` 必须检查 CIF size > 0
- **修复**：增加 timeout + 必要时重启 Pod 刷新 GPU 状态

### 超时时间速查

| 序列长度 | 建议 timeout | 实测耗时 |
|---------|-------------|---------|
| <200aa | 300s | 158-330s |
| 200-600aa | 7200s | 702-1269s |
| 600-1200aa | 7200s | 2000-2223s |
| 1200-1600aa | 7200s | 6443s+ |
| >2000aa | 跳过 | C550 硬限制，送 H200 |

### 清理残留进程

```bash
kubectl exec -n studio-ams $POD -- pkill -f run_alphafold
```

### 僵尸进程诊断

`ps aux` 显示 `<defunct>`（Z 状态）+ GPU 0 显存占用 + log 冻结在最后一条 RUN → 父进程已死。立即重启 batch（已完成 CIF 自动跳过）。

## 十一、MACA GPU 常见问题

### Compute Queue type:21 Bug

**症状**：某样本推理后所有后续提交全部失败。`dmesg` 显示：
```
[MXKW][E]queues.c:826: [mxkwCreateQueueBlock][Hint]
ioctl create queue block timeout, gpu_id:XXXXX type:21.
```
进程 SIGKILL (exit 137) 或超时 (exit 124)。

**修复**：`export MACA_MPS_MODE=1`。这是沐曦官方修复，解决驱动 Queue 句柄泄漏。

**注意**：此 bug 是节点级（非 Pod 级），同节点所有 Pod 共享 queue 表。换 Pod 无效，必须换节点或重启驱动。

### 不同 host 性能差异

同一样本在 host-151 可跑通但 host-137 超时。Pod 迁移后需重新验证 timeout。

## 十二、并行推理：Deployment 自动 Shard

单个 Pod 串行跑太慢时，用 Deployment 8 路并行 shard。

### 原理

Allocator 脚本用 `os.mkdir()` 原子操作在 PVC 上注册 hostname → 按字母排序确定 shard index。Pod 重启后 reclaim 相同 shard → `is_done()` 跳过已完成。

### 步骤

1. 上传 allocator 脚本到 PVC
2. 清理旧分配状态：`rm -rf /data/.shard_alloc`
3. Patch deployment command 为 allocator 脚本
4. Scale to 8：`kubectl scale deploy <name> -n studio-ams --replicas=8`
5. 验证 8 路进程

**⚠️ 不要用 `kubectl exec ... nohup ... &` 手动启动 shard**：进程随 exec 会话退出而死亡。

**⚠️ PVC log 跨 Pod 共享**：`>>` 追加写入同文件，Pod 重启后旧日志残留。验证进度看 PVC output 目录数量。

**⚠️ 全部完成后 CrashLoop**：所有样本完成 → shard 退出 → K8s 重启 → 再次全跳过 → 再次退出。如果确认所有样本完成，CrashLoop 是正常终态，不需要恢复。

## 十三、自愈与监控

### Deployment 级自愈

`while true` 守护循环保证 batch 退出后自动重启，Deployment controller 保证 Pod 被驱逐后重新调度。PVC 持久化数据，Pod 重启不丢进度。

### Cron 监控作业

现有监控 cron（自动检测 AF3 batch 进程状态并恢复）：

| Cron ID | 名称 | 间隔 | 说明 |
|---------|------|------|------|
| c40dcfd01d53 | C550 ABAG+PL Watchdog | 30min | 检测 Pod 存活 + batch 进程状态，死进程自动重启 |
| c940afc194f7 | ABAG+PL Backup | 每小时 | 增量备份 PVC → 本地 |
| 001245057f9f | AF3 ABAG+PL watchdog | 30min | 综合监控（C550+H200+长序列分片） |

### 常见恢复操作

```bash
# 1. batch 进程挂死 → pkill 后 while true 自动重拉
kubectl exec -n studio-ams <pod> -c alphafold3-main -- pkill -f run_af3_batch

# 2. GPU type:21 错误 → rollout restart（建新 Pod 换新 GPU 状态）
kubectl rollout restart deploy/<name> -n studio-ams

# 3. Pod 消失 → Deployment 自动重建（PVC 数据不丢）
# 等待新 Pod Ready 后，batch 自动从 skip 逻辑续跑
```

## 十四、已知问题速查

| 问题 | 症状 | 修复 |
|------|------|------|
| **MACA type:21** | 推理第一样本就挂 | `MACA_MPS_MODE=1` |
| **kubectl cp 静默失败** | 文件已传但内容/大小不对 | 用 tar pipe |
| **mx-smi 僵尸** | 命令挂起 | 用 `ps aux` 替代 |
| **OVN IP 冲突** | Pod 永久 ContainerCreating | 用 rollout restart 代替 delete pod |
| **空 CIF** | AF3 崩溃先写空文件 | `is_done()` 检查 size > 0 |
| **Pod 重启丢 /tmp/** | /tmp/ 数据丢失 | 完成后立即下载，中途定期备份 |
| **Liveness Probe** | 长时间推理中 Pod 被杀 | 通知平台同事调整 `timeoutSeconds` |
| **多容器 Pod** | exec 进错容器 | `-c <container>` |
| **系统 curl** | Anaconda curl 连不上内网 | `env PATH=/usr/bin:/bin` |

## 十五、备选：REST API 未覆盖模型的 Pod 直跑

以下模型 REST API 未实现或输出不完整，只能通过 kubectl exec 直跑：

| 模型 | Pod 名 pattern | CLI 命令 |
|------|---------------|----------|
| boltzgen | `boltzgen-1-*` | `boltzgen run <yaml> --output <dir> --protocol protein-anything --num_designs 1 --moldir /opt/boltzgen_inference_data --use_kernels false` |
| rfdiffusion | `rfdiffusion-1-*` | `/opt/conda/envs/py312/bin/rfdiffusion` |

### Boltzgen 直跑流程

```bash
# 1. 获取 Pod
POD=$(kubectl get pods -n studio-ams | grep boltzgen | awk '{print $1}')

# 2. 上传输入
tar cf - *.yaml | kubectl exec -i studio-ams/$POD -- tar xf - -C /tmp/inputs/

# 3. 单样本推理
kubectl exec studio-ams/$POD -- boltzgen run /tmp/inputs/sample.yaml \
  --output /tmp/out \
  --protocol protein-anything \
  --num_designs 1 \
  --moldir /opt/boltzgen_inference_data \
  --use_kernels false
```

**⚠️ C550 上 `--use_kernels` 必须为 false**。
