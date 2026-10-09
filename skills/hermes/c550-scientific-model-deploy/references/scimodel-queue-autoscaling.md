# 科学模型队列与动态扩容机制（源码结论）

来源：`/Users/huron/code/ai_lab/inference-gateway-sd` 代码分析（task-dispatcher、instance-operator、scientific-router 插件）。回答"发送多少个推理请求会扩容、怎么 queue"这类问题时按本文推导，不要凭印象。

## 任务链路（三层 queue）

1. 用户 `POST /v1/scimodel/tasks` → 科学模型网关（10.12.111.133:10018）→ L2 Higress `scientific-router` 插件拦截
2. 插件生成 task_id，Redis 写 `scimodel:task:<id>`（status=queued，TTL 3600s），消息发 Kafka topic `scimodel-<模型名>`，立即返回 task_id（提交异步）
3. `task-dispatcher`（每模型独立 consumer group）从 Kafka 消费，背压通过后 HTTP POST 到模型后端（nginx → Pod:8000），成功后删 Redis queued 状态；推送失败重试 120 次（5s 间隔）后 MarkFailed
4. 模型服务内部队列（pending/running 目录 + 线程池），`/health` 暴露 `global_pending`、`global_running`、`this_instance_running`、`max_workers`

## dispatcher 背压（capacity.go）

每 10s 轮询后端 /health：`available = capacityBuffer - global_pending`（负数取 0），仅当 `available - inFlight > 0` 才继续从 Kafka 拉取下发；无容量每 5s 等待重试，任务积压在 Kafka。

capacityBuffer：mmseqs=5，其余模型=3（task-dispatcher/config.yaml）。刻意让后端最多积压 buffer 个 pending——这正是扩容信号。

## 队列模式自动扩容（instance_controller.go）

配置载体：`ModelPolicy` CRD（与 Instance 同名、operator 自动创建/删除），`spec.autoScaling.{enabled,mode:queue,minReplicas,maxReplicas}`。开启后与手动扩缩容互斥（API 直接报错）。

每 30s reconcile 一次，直连各 Pod :8000/health 取快照（多 Pod 快照取 max 合并 pending/running、求和 this_instance_running）：

```
totalTasks = global_pending + global_running
capacityPerInstance = max_workers   # 优先级: health.max_workers > queueConfig.capacityPerInstance > 1；当前 max_workers=2
neededReplicas = ceil(totalTasks / capacityPerInstance)  # 夹在 [minReplicas, maxReplicas]
```

触发点推算（min=1, max_workers=2）：并发 1–2 个任务不扩；**第 3 个并发任务触发 1→2 副本**，之后每多 2 个任务 +1 副本，上限 maxReplicas（默认 10）。只统计已推到后端进入 pending/running 的任务——还在 Kafka 积压的不算，所以大批量提交时扩容是逐级爬升（dispatcher 推 3 个 → 扩 2 副本 → 新 Pod ready → 继续推 → 再扩）。

扩缩容执行细节：
- 扩容批量直达目标值（非 +1 递增，避免 GPU 初始化慢导致连续扩到上限）；「N 个 Deployment 各 1 副本」模式，缩容可精确选 Pod；序号按缺失 index 补位（[1,4,5] 扩 1 个补 2 号）
- 扩容后自动更新 nginx ConfigMap upstream + sidecar `nginx -s reload` 热加载
- 缩容条件苛刻：仅 totalTasks==0 且 this_instance_running==0 缩到 minReplicas；只删 running=0 的 Pod，先标 scaleDown → 摘 nginx 流量 → 等 30s 排空 → 删 Deployment
- HPA 模式 CRD 有定义但未实现；VASP 是 CPU 服务、单任务串行，不走此扩容

## 线上验证路径

- AD 登录：`POST http://10.12.111.133:10018/api/v1/auth/ldap/login`（username/password JSON），返回 token + user（authSource=ldap, status=active 才算开通）；token 15 天有效
- 模型自描述：`GET /v1/scimodel/info` 必须带 `x-original-model: <model>` header，否则 400
- 查线上实际 min/max：kubectl 读 ModelPolicy（`kubectl get modelpolicies -A`）或 inference-manager API `GET /api/v1/model-policies/<instance>?namespace=...`。分析报告中的扩缩容阈值必须以线上 ModelPolicy 配置为准，代码默认值（min=1/max=10）只是兜底
- 网络可达性因环境而异：科学模型网关 HTTP 通常可达；子集群 K8s API（vc-c550-ai4s-sys:443、jiaofu:33434）与 MetaX 38080 可能不可达——先 curl 探活再选路径；kubectl 连不上时改走网关 HTTP API 或跳板 VM（10.120.17.201），并设 `--request-timeout`，不要反复重试挂死的连接

## 代码定位（inference-gateway-sd）

| 内容 | 位置 |
| --- | --- |
| 背压算法 / health 解析 | task-dispatcher/internal/capacity/capacity.go |
| Kafka 消费、推送重试、Redis 状态机 | task-dispatcher/internal/consumer/consumer.go |
| 模型 topic/buffer 配置 | task-dispatcher/config.yaml |
| 扩缩容公式与决策 | instance-operator/internal/controller/instance_controller.go（ReconcileAutoScaling） |
| 任务拦截入队 | higress/plugins/scientific-router/plugin/main.go |
| 设计/实测文档 | docs/11-KAFKA-QUEUE-DESIGN.md、test/05-AUTO_SCALING_TEST.md |
