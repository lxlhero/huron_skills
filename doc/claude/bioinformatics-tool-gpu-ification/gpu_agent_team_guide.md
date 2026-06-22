═══════════════════════════════════════════════════
  生信工具 GPU 加速 Agent Team — 架构与使用手册
═══════════════════════════════════════════════════

核心文件路径
  方法论文档（67 条踩坑）：huron_skills/skills/claude/bioinformatics-tool-gpu-ification/SKILL.md
  团队详细设计：         huron_skills/doc/claude/bioinformatics-tool-gpu-ification/bioinformatics-tool-gpu_agent_team.md
  Slash command 实现：   .claude/commands/gpu-*.md（共 13 个）


═══ 一、Agent 一览（13 个）═══

  ┌─────────────────────┬──────────────────────────┬─────────────────────────────────┐
  │ Slash Command       │ 角色                     │ 触发时机                        │
  ├─────────────────────┼──────────────────────────┼─────────────────────────────────┤
  │ /gpu-team           │ 调度 agent（主入口）      │ 用户发起任务，永远从这里开始     │
  │ /gpu-logging        │ 日志 agent               │ 任务开始时拉起，全程异步运行     │
  │ /gpu-benchmark      │ benchmark agent          │ 任务开始后立即并行启动           │
  │ /gpu-image-builder  │ 镜像构建 agent           │ Step 2（L1）、Step 6（L2）、v1.0 │
  │ /gpu-profiling      │ profiling agent + 循环控制│ Step 3；驱动 Step 5 开发循环    │
  │ /gpu-feasibility    │ GPU 可行性分析 agent      │ Step 3，由 profiling agent 调用  │
  │ /gpu-rjob           │ rjob 提交 agent          │ 任何需要提交集群任务的步骤       │
  │ /gpu-dev            │ GPU 加速开发 agent        │ Step 5，编写和调试 GPU kernel    │
  │ /gpu-code-reviewer  │ 代码审核 agent           │ Step 5，gpu-dev 写完后、进集群前 │
  │ /gpu-module-tester  │ 模块测试 agent           │ Step 5，审核通过后提交集群验证   │
  │ /gpu-e2e-tester     │ 端到端测试 agent         │ Step 4 + 7，CPU/GPU 实时对比    │
  │ /gpu-problem-analyst│ 问题分析 agent           │ 任意步骤出错时由调度 agent 调用  │
  │ /gpu-doc-writer     │ 文档 agent               │ Step 8，生成飞书格式文档         │
  └─────────────────────┴──────────────────────────┴─────────────────────────────────┘


═══ 二、任务模式 ═══

── 模式 A — 全流程 GPU 化（新工具从零开始）──

    /gpu-team <工具名> A

  流程：Step 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8（全部步骤）

  需要提供：
    · 工具名称和代码路径
    · 数据来源（私有数据路径 或 使用公开数据集）

  交付物：
    · <tool>-gpu:v1.0 镜像（支持 <TOOL>_DEVICE=gpu|cpu 切换）
    · 飞书格式用户文档 + 精度速度分析报告


── 模式 B — 重跑验证并修复（已有镜像，换 benchmark 验证）──

    /gpu-team <工具名> B <镜像名>

  流程：CPU + GPU 在同一 rjob 里实时对比 → 精度不达标则自动修复

  特点：
    · 无需提供 gold standard 路径，每次重新跑 CPU baseline
    · benchmark agent 自动寻找真实数据（可指定私有数据路径）


── 模式 C — 修复已知问题（已定位到具体模块）──

    /gpu-team <工具名> C <镜像名> "<模块名> <问题描述>"

  示例：
    /gpu-team susieR C susier-gpu:v1.0 "_update_sigma2 精度FAIL，PIP r=0.87"

  流程：跳过发现阶段，直接进 Step 5 debug 循环 → 修完跑 E2E 验证

  需要提供：
    · 已有镜像名
    · 哪个模块有问题 + 具体症状（精度数值、报错信息）


── 模式 D — 私有数据验证并修复（数据 + 镜像都由用户提供）──

    /gpu-team <工具名> D <镜像名> "<路径1> <路径2> ..."

  示例：
    /gpu-team gsMap D gsmap-gpu:v1.0 "/mnt/gpfs/spatial/ /data/gwas_sumstats/"

  支持多个互补路径（如空间转录组 + GWAS 汇总统计分别对应工具不同输入）

  流程：
    1. benchmark agent 分析所有数据源，判断能否互补构建完整工具输入
    2. 输出兼容性报告，等待用户确认
    3. 确认后构建 benchmark，写入 GPFS
    4. 同一 rjob 跑 CPU + GPU，实时对比精度和速度
    5. 精度不达标 → 自动修复循环

  需要提供：
    · 已有镜像名
    · 一个或多个数据路径（空格分隔，GPFS 或本地路径均可）


═══ 三、Step 5 开发循环详解 ═══

  gpu-dev 写代码
      ↓
  gpu-code-reviewer 本地静态检查（秒级，零集群成本）
      ├── FAIL → 打回 gpu-dev 修复（不进集群）
      └── PASS ↓
  gpu-module-tester 提交 rjob 集群测试（分钟级）
      ├── 精度 FAIL → gpu-dev debug（最多 5 次重试）
      └── 精度 PASS → 下一个模块

  代码审核检查点（gpu-code-reviewer）：
    P0  语法：ast.parse() 无报错，import 存在
    P1  算法路径：数值路径与原版一致（非仅数学等价）
        float64 全程，sigma² 全 trace 校正
    P2  常见 GPU bug：diagonal() 替代 diag()、y.squeeze() 防御
        sparse.mv() 不存在于 PyTorch 2.3.1
    P3  CPU/GPU 切换：<TOOL>_DEVICE 环境变量控制，CPU 路径委托原版
    P4  性能（非阻塞建议）：批量化优先，避免 for 循环逐元素操作


═══ 四、精度标准 ═══

  对比基准：原版工具最终用户输出（禁止用自写 CPU 镜像版对比）

  ┌─────────────────────────────────┬──────────────────┐
  │ 输出类型                        │ 精度阈值         │
  ├─────────────────────────────────┼──────────────────┤
  │ 连续评分（PIP、LD score、beta） │ Pearson r > 0.99 │
  │ p 值                            │ Pearson r > 0.999│
  │ 方差参数（sigma²、h²）          │ ratio ∈ 0.99~1.01│
  │ 可信集 / 显著集合（CS、QTL）   │ Jaccard > 0.95   │
  │ 二进制分类结果                  │ F1 > 0.95        │
  └─────────────────────────────────┴──────────────────┘

  特殊情况：算法非凸导致多局部最优时，计算 ELBO 确认 |ΔELBO| < 1 nat，
            视为等价，文档化说明，不强制 Pearson r 达标。


═══ 五、镜像版本规范 ═══

  ┌──────────────┬─────────────────────────────────────┐
  │ Tag          │ 含义                                │
  ├──────────────┼─────────────────────────────────────┤
  │ :<date>-base │ L1：原工具 + CUDA/PyTorch，无 kernel │
  │ :v0.x        │ L2：GPU kernel 内化，调试版          │
  │ :v1.0        │ 正式交付版，E2E 精度速度全部达标     │
  └──────────────┴─────────────────────────────────────┘

  v1.0 交付条件（全部满足）：
    · 真实数据 E2E 精度达标（见上表）
    · E2E 加速 ≥ 15%
    · 镜像支持 <TOOL>_DEVICE=gpu|cpu 切换
    · 飞书文档已生成


═══ 六、铁律 ═══

  1. 精度优先          先对齐精度，再提升速度，不能为速度牺牲精度
  2. 真实数据          E2E 必须用真实生物数据；smoke test 才允许合成数据
  3. benchmark 独立    E2E 与 profiling 数据集独立；只有一份时 8:2 划分
  4. bash 内联         所有 rjob 一律 bash 内联，不依赖 GPFS 外部脚本
  5. 不重建镜像调试    模块调试用 L1 base + GPFS mount，通过后再内化 L2
  6. 15% 门槛          Amdahl 预期 E2E 加速 < 1.15× 时终止 GPU 化
  7. 切换是交付物      CPU/GPU 环境变量切换必须实现，不是可选项


═══ 七、问题排查路径 ═══

  任意步骤出错
      → 上报调度 agent（附 decision_id + 错误描述）
      → /gpu-problem-analyst 诊断
          读日志链 + 检索 SKILL.md pitfall 列表
      → 输出：根因 + 修复建议 + 分配给哪个 agent
      → 对应 agent 修复 → 重入失败步骤

  日志路径：/mnt/shared-storage-gpfs2/<project>/logs/<decision_id>.json
  ID 格式： {task_id}/{step}/{agent}/{seq:03d}
  示例：    susieR-gpu-20260622/step5/gpu-dev/003


═══ 八、已交付案例 ═══

  | 工具     | 语言 | 热点                          | 加速      | 镜像版本         |
  |----------|------|-------------------------------|-----------|-----------------|
  | susieR   | R    | tcrossprod（XtX GEMV）        | fit 24×   | susier-gpu:v1.0 |
  | gsMap    | Python| latent_to_gene cosine+gmean  | 2.6~15.6× | gsmap-gpu:v1.8.3|
  | SCAVENGE | R    | randomWalk_sparse（SpMV×1000）| ~100×（预期）| 进行中       |
