════════════════════════════════════════════════════
  生信工具 GPU 加速 — Agent Team 架构设计文档
════════════════════════════════════════════════════

参考方法论：
  /Users/huron/code/ai_lab/huron_skills/skills/claude/bioinformatics-tool-gpu-ification/SKILL.md


═══ 一、任务模式 ═══

调度 agent 根据输入判断从哪个步骤进入，不强制全流程。

  | 模式 | 触发条件 | 入口步骤 |
  |------|---------|---------|
  | A. 全流程 GPU 化 | 新工具，从零开始 | Step 1 → Step 8 |
  | B. 重跑验证并修复 | 已有镜像，需换数据重新验证；精度不达标则自动修复 | Step 4 → Step 7，失败则 → Step 5 → 6 → 7 |
  | C. 修复已知问题 | 已定位具体模块，直接进 debug 循环 | Step 5 → Step 6 → Step 7 |
  | D. 私有数据验证并修复 | 用户提供私有数据 + 已有镜像；构建 benchmark 后跑 E2E，不达标则修复 | benchmark 分析 → Step 4+7 → 失败则 Step 5 → 6 → 7 |

调度 agent 接收任务时必须明确模式，并将已有信息（镜像名、上次失败原因）传递给对应 agent。


═══ 二、完整流程 ═══

  Step 1  调度 agent
          接收任务，制定方案，并行启动 logging agent 和 benchmark agent

          ├──► logging agent    【立即启动】全程异步记录所有决策和事件
          └──► benchmark agent  【立即启动】准备 benchmark 数据（耗时，尽早开始）

  Step 2  构建镜像 agent（L1 build）
          构建 L1 base 镜像（原工具 + CUDA/PyTorch 依赖）
          本地 smoke test → tag push :<date>-base

  Step 3  profiling agent
          向 benchmark agent 索要中等规模 benchmark
          编写 profiling 脚本，交给 rjob agent 在集群上跑
          分析热点模块 → 交给 GPU 可行性 agent 评估各模块加速潜力
          收到回复后代入 Amdahl's Law 计算 E2E 预期提升：

              E2E_speedup = 1 / ((1 - P) + P / S)
              P = 可 GPU 化模块占 E2E 总时间比例
              S = 该模块预估 GPU 加速倍数

          E2E 预期提升 < 15%  →  返回调度 agent（不值得 GPU 化，终止）
          E2E 预期提升 ≥ 15%  →  进入 Step 4

  Step 4  端到端测试 agent（CPU baseline）
          向 benchmark agent 索要 E2E benchmark
          ⚠ 必须与 Step 3 profiling benchmark 完全独立（不同数据集）
          用 rjob agent 跑原版工具完整 pipeline
          统计各阶段时间 + 最终输出
          保存至 GPFS gold standard 目录：
              /mnt/shared-storage-gpfs2/<project>/e2e_baseline/

  Step 5  GPU 加速开发循环（profiling agent 驱动，逐模块串行）

          profiling agent【循环控制者】维护待处理模块队列，逐个驱动：

          ① 将当前模块代码 + 可行性方案交给 GPU 加速开发 agent
          ② GPU 加速开发 agent 写完代码，交给代码审核 agent
                审核 FAIL → 打回 GPU 加速开发 agent 修复（本地，不进集群）
                审核 PASS → 通知模块测试 agent 提交集群
          ③ 等待模块测试 agent 返回结果
                PASS → 取队列下一模块，重复 ①
                       队列为空 → 通知调度 agent 进入 Step 6
                FAIL → 转 GPU 加速开发 agent debug
                       同一模块最多 5 次重试，超限上报调度 agent

          GPU 代码写入 GPFS 路径：
              /mnt/shared-storage-gpfs2/<project>/src/<module>_gpu.py

          模块测试用【L1 base 镜像 + GPFS mount kernel】提交集群
              不重建镜像，每次改代码只需同步 GPFS，秒级生效

  Step 6  构建镜像 agent（L2 build）
          将 GPFS 上已验证的 GPU kernel 内化进镜像（COPY，不做 runtime patch）
          本地 smoke test（CPU + GPU 两种模式各跑一遍）
          tag push :v0.x

  Step 7  端到端测试 agent（GPU vs CPU 对比）
          用 rjob agent 以 L2 镜像跑 GPU 版完整 pipeline（真实 benchmark）
          同一 rjob 内用 <TOOL>_DEVICE 切换，实时对比：
              精度 PASS + 速度 ≥ 1.15×  →  通知镜像构建 agent tag v1.0，进入 Step 8
              精度 FAIL                 →  反馈给调度 agent，重入 Step 5
              速度不达标                →  反馈给调度 agent（重新评估可行性）

  Step 8  文档 agent
          收集 GPFS 上的 profiling 热点报告、CPU/GPU E2E 结果、模块精度对比表
          撰写飞书格式用户文档 + 精度速度分析报告

  ── 任意步骤出错时的通用路径 ──

          出错 → 上报调度 agent（附 decision_id + 错误描述）
               → 调度 agent 转交问题分析 agent
               → 问题分析 agent 读日志链 + 检索 SKILL.md pitfall
               → 输出根因 + 修复建议 + 分配给哪个 agent
               → 对应 agent 修复 → 重入失败步骤


═══ 三、角色定义（13 个）═══

── 1. 调度 agent ──

  接收任务时必须明确：
    · 工具名、代码路径、语言（R/Python）
    · 任务模式（A/B/C/D）
    · 模式 B/C：已有镜像名 + 上次失败的具体现象
    · 模式 C：哪个模块有问题 + 具体症状（精度数值、报错）
    · 数据来源：私有路径 或 公开数据集

  职责：根据模式决定入口步骤；并行启动 benchmark agent 和 logging agent；
        接收异常 → 转交问题分析 agent → 分发修复任务；最终验收 v1.0 交付物

── 2. 构建镜像 agent ──

  L1 build（Step 2）
    原工具 + CUDA/PyTorch 依赖，--platform linux/amd64
    smoke test：python3 -c "import tool; import torch"
    tag push :<date>-base

  L2 build（Step 6）
    从 GPFS COPY 已验证 kernel（不做 runtime patch）
    smoke test：TOOL_DEVICE=cpu 和 TOOL_DEVICE=gpu 各跑一遍
    tag push :v0.x

  v1.0 tag（Step 7 通过后）
    docker tag :v0.x :v1.0 && docker push

  版本规则：v0.x = 开发迭代，v1.0 = 正式交付

── 3. rjob agent ──

  所有任务一律 bash 内联（rjob submit -- bash -c '...'），禁止依赖 GPFS 外部脚本
  监控：每 2 分钟查询状态，超 30 分钟 STARTING 则取消重提（最多 3 次）

  必带参数（所有 rjob 共用）：
      rjob submit \
        --namespace ailab-ma4agismall \
        --private-machine=group \
        --charged-group=ma4agismall_gpu \
        --task-type=normal \
        --gpu=1 --cpu=8 --memory=60000 \
        --mount=gpfs://gpfs2/liangxiuliang-2:/mnt/shared-storage-gpfs2/liangxiuliang-2 \
        --image=<镜像> \
        -- bash -c '...'

  SSH 地址：huron-dev-1.liangxiuliang+root.ailab-ma4agismall.ws@h.pjlab.org.cn

  引号规则（R 工具必知）：
    · 外层 heredoc：bash << 'REMOTE_EOF'（单引号防本地变量展开）
    · R 代码 heredoc：<<'"'"'REOF'"'"'（防 bash -c 内单引号冲突）
    · R 代码内路径硬编码，不用 $VAR

── 4. profiling agent ──

  工具：R 用 Rprof / profvis，Python 用 cProfile / py-spy
  通过 rjob agent 在集群上用真实数据跑 profiling
  整理热点模块（各模块耗时 + 占 E2E 比例），过滤 < 10% 的模块
  将热点模块交给 GPU 可行性 agent 评估，收回预估加速倍数后代入 Amdahl 计算
  同时担任 Step 5 循环控制者：维护模块队列，逐个驱动开发→审核→测试闭环

── 5. GPU 可行性 agent ──

  输入：热点模块代码列表
  分析每个模块是否适合 GPU 化：
    高潜力：矩阵乘法、BLAS 运算、向量化运算、可批量化的独立重复计算
    低潜力：I/O 密集、复杂控制流、串行状态依赖、数据规模 < 10K 元素

  输出结构（每个模块）：
    | 模块名 | 计算特征 | GPU 化方案 | 预估加速倍数 | 精度风险 | 推荐 |

  预估倍数需标注依据（SKILL.md 同类操作实测数据 或 文献）

── 6. benchmark agent ──

  数据来源优先级：① 用户私有数据  ② 公开数据集  ③ 合成数据（仅 smoke test）

  私有数据分析流程（多路径互补支持）：
    Step 1  逐个扫描每个路径（格式、大小、数量）
    Step 2  读取工具输入要求（所有必需字段）
    Step 3  单独兼容性判断（每个路径）
    Step 4  互补性判断（多路径合并能否凑出完整工具输入）
    Step 5  输出分析报告，等待用户确认
    Step 6  确认后执行数据准备，写入 GPFS，提供可复现脚本

  数据命名与独立性要求：
    bench_profiling_<tool>  →  开发调试用，允许参与调参
    bench_e2e_<tool>        →  最终验证用，必须与 profiling 数据独立
                               只有一份数据时 8:2 划分并在报告注明

── 7. 端到端测试 agent ──

  Step 4（CPU baseline）：L1 base 镜像跑原版工具，记录时间 + 最终输出，保存至 GPFS

  Step 7（GPU vs CPU 对比）：L2 镜像，同一 rjob 内用 <TOOL>_DEVICE 切换
    精度达标 + 速度 ≥ 1.15×  →  通知调度 agent 验收通过
    任一不达标               →  反馈具体失败数值给调度 agent

  E2E 铁律：必须用 bench_e2e 真实数据；比的是最终用户输出，不是中间变量

── 8. 模块测试 agent ──

  用 L1 base 镜像 + GPFS mount kernel 提交集群（不重建镜像）
  对比模块输出精度 + 速度
  PASS → 通知 profiling agent（循环控制者）继续下一模块
  FAIL → 将具体差异（哪个输出、数值差异、数据规模）反馈给 GPU 加速开发 agent

── 9. GPU 加速开发 agent ──

  架构：R 工具用 R 控制流 + Python/PyTorch GPU kernel + reticulate 桥接
  调试模式：代码写入 GPFS，base 镜像 + mount 加载，不重建镜像
  必须实现 CPU/GPU 切换：<TOOL>_DEVICE=gpu|cpu 环境变量控制
    CPU 路径委托原版实现（不自己重写），用户 API 不变
  收到审核 FAIL 或测试 FAIL 后修复，每次修改后通知对应 agent 重测

── 10. 代码审核 agent ──

  坐在 gpu-dev 和 gpu-module-tester 之间，本地静态检查，零集群成本

  审核优先级：
    P0（必须通过，否则打回）
      ast.parse() 无报错，所有 import 存在
    P1（精度核心，必须通过）
      GPU 数值路径与原版一致（非仅数学等价）
      float64 全程，sigma² 使用全 trace 校正
    P2（常见 GPU bug，必须通过）
      torch.diag(large_tensor) → 改为 .diagonal()
      reticulate 传入 y 向量：有 y.squeeze() 防御
      torch.sparse.mv() 不存在于 PyTorch 2.3.1，用 torch.mv()
    P3（切换实现，必须通过）
      有 <TOOL>_DEVICE 环境变量控制分支
      CPU 路径委托原版，不自己重写
    P4（性能，建议性，不阻塞）
      无 for 循环逐元素操作大矩阵
      batch 操作优先

  输出：PASS / FAIL（附具体条目）/ WARN（仅建议）

── 11. 文档 agent ──

  输入来源（均从 GPFS 读取）：
    · profiling 热点报告（各模块耗时占比）
    · Step 4 CPU E2E 各阶段时间
    · Step 7 GPU E2E 各阶段时间 + 精度对比数值
    · 模块级精度速度对比（模块测试 agent 汇总）

  输出格式：飞书 Markdown（═ 分隔线、| 表格 |、无 ``` 代码围栏）
    · 用户使用手册（切换方式、环境变量、接口说明）
    · 精度速度分析报告（各规模结果、Amdahl 分析、已知局限）

── 12. logging agent ──

  全程运行，异步 fire-and-forget（不阻塞发送方）
  结构化 JSON 写入 GPFS：/mnt/shared-storage-gpfs2/<project>/logs/

  日志格式：
      {
        "decision_id": "{task_id}/{step}/{agent}/{seq:03d}",
        "timestamp":   "ISO8601",
        "agent":       "gpu-dev",
        "step":        "step5",
        "event_type":  "decision | action | result | error | escalation",
        "summary":     "修改 _update_sigma2，用 diagonal() 替换 diag()",
        "inputs":      {"module": "scavenge_gpu.py", "attempt": 2},
        "outputs":     {"pearson_r": 0.9996}
      }

  必须记录：rjob 提交、精度判断、agent 间通信、调度 agent 决策

── 13. 问题分析 agent ──

  触发：任意 agent 上报问题 → 调度 agent 转交（附 decision_id + 错误描述）
  诊断：读日志链 → 对比预期 vs 实际 → 检索 SKILL.md pitfall 列表

  输出格式：
      根因：<一句话描述>
      证据：<哪条日志支持这一判断>
      修复建议：<具体操作>
      分配给：<专职 agent 名称>
      置信度：高 / 中 / 低

  职责边界：只做诊断，不写代码、不提交 rjob、不直接操作数据
  自身出错：直接上报调度 agent，不递归调用自身


═══ 四、精度标准 ═══

  对比基准：原版工具最终用户输出（禁止用自写 CPU 镜像版对比）

  | 输出类型 | 精度阈值 | 说明 |
  |---------|---------|------|
  | 连续评分（PIP、LD score、beta）| Pearson r > 0.99 | |
  | p 值 | Pearson r > 0.999 | 跨数量级，要求更严 |
  | 方差参数（sigma²、h²）| ratio ∈ 0.99~1.01 | 偏离 1% 以内 |
  | 可信集 / 显著集合（CS、QTL）| Jaccard > 0.95 | 大小 + 成员一致性 |
  | 二进制分类结果 | F1 > 0.95 | |

  特殊情况：算法非凸导致多局部最优时，计算 ELBO 确认 |ΔELBO| < 1 nat，
            视为等价，文档化说明，不强制 Pearson r 达标。


═══ 五、铁律 ═══

  1. 精度优先      先对齐精度，再提升速度，不能为速度牺牲精度
  2. 真实数据      E2E 必须用真实生物数据；smoke test 才允许合成数据
  3. benchmark 独立 E2E 与 profiling 数据集独立；只有一份时 8:2 划分并注明
  4. bash 内联     所有 rjob 一律 bash 内联，禁止依赖 GPFS 外部脚本
  5. 不重建镜像    模块调试用 L1 base + GPFS mount，通过后再内化进 L2
  6. 15% 门槛     Amdahl 预期 E2E 加速 < 1.15× 时终止 GPU 化
  7. 切换是交付物  v1.0 必须支持 <TOOL>_DEVICE=gpu|cpu，CPU 路径委托原版
