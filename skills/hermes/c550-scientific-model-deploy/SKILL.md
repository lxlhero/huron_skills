---
name: c550-scientific-model-deploy
description: "C550 推理平台科学模型部署全流程。涵盖模板导入、Deployment/Service创建、Instance/ModelInstance CRD注册与status同步、nginx-proxy路由更新、推理API说明、模型分类测试（序列型/文件型）、alphafold3输入格式及压测结果、新namespace迁移陷阱（operator/UI/bundle硬编码studio-ams修复方案）。前置依赖：平台基础设施须已部署（见 c550-platform-deploy）。"
version: 1.1.0
metadata:
  hermes:
    tags: [devops, mlops, k8s, inference, c550, deployment, scientific-model]
  supersedes: c550-inference-platform-deploy
  depends_on: [c550-platform-deploy]
---

# C550 科学模型部署

## 前置条件

平台基础设施必须已部署完成（见 `c550-platform-deploy`），验证清单通过后再执行本文档步骤。

## 1. 模型架构

每个模型 = 1 个 Deployment + 1 个 Service（ClusterIP）：

  image: registry2.d.pjlab.org.cn/ai4s/scientific-model-server:v2.0.0
  env: MODEL_NAME=<name>
  port: 8000
  volumeMounts: /mnt/afs (AFS 共享存储)

完整 Deployment YAML 示例参考 `deploy_inference_platform/deploy_scientific_models/manifests/esm2.yaml`。

## 2. 模板导入

模板是 label `inference-manager=template` 的 ConfigMap，命名规范 `inference-manager-template-<name>`。

从旧集群导出导入的流程：

  export OLD_K=config-vc-c550-ai4s-sys.yaml
  export NEW_K=config-vc-c550-jiaofu-test.yaml
  OLD_NS=studio-ams
  NEW_NS=vc-c550-jiaofu-test

  for model in alphafold3 ankh3 ...; do
    cm="inference-manager-template-${model}"
    KUBECONFIG=$OLD_K kubectl get cm $cm -n $OLD_NS -o json | \
      jq 'del(.metadata.uid, .metadata.resourceVersion, .metadata.creationTimestamp,
              .metadata.managedFields, .metadata.annotations["kubectl.kubernetes.io/last-applied-configuration"]) | 
          .metadata.namespace = "'$NEW_NS'"' | \
      KUBECONFIG=$NEW_K kubectl apply -f -
  done

注意事项：
  - 模板包含 Deployment YAML + model info + port config
  - 导入后验证：`/api/v1/templates` 返回 20 条
  - 模板内容中的 namespace 引用可能需要适配目标集群

## 3. 首次部署数据初始化

新集群 inference-manager 启动后，Cluster、Template、ModelInstance 三类数据全部为空，需手动初始化。

### 3.1 Cluster ConfigMap

  kubectl create configmap inference-manager-cluster-metax \
    -n vc-c550-jiaofu-test \
    --from-literal=endpoint=10.140.158.130:38080 \
    --from-literal=dnat=10.140.158.130:38080 \
    --from-literal=type=ip \
    --from-literal=status=active \
    --from-literal=cluster='{"displayName":"沐曦集群","clusterType":"ip","DNAT":"10.140.158.130:38080","externalService":"metax-external","grafanaDatasourceUid":"P25CDD04CF7FBA6B1"}'
  kubectl label configmap inference-manager-cluster-metax -n vc-c550-jiaofu-test inference-manager=cluster

⚠️ displayName 必须在 cluster JSON 内，不能作为独立 data key，否则 API 显示 "-"。

### 3.2 ModelInstance CRD 批量状态同步

ModelInstance CRD 创建后 status 为空（phase="" readyReplicas=0 health=false），instance-operator 不自动 reconcile。需手动从实际 Running Pod 同步：

  for model in <list>; do
    pod=$(kubectl get pod -n vc-c550-jiaofu-test -l app=$model -o jsonpath='{.items[0].metadata.name}')
    ip=$(kubectl get pod -n vc-c550-jiaofu-test -l app=$model -o jsonpath='{.items[0].status.podIP}')
    kubectl patch modelinstance $model -n vc-c550-jiaofu-test --type merge -p '{
      "status": {
        "phase": "Running", "readyReplicas": 1, "totalReplicas": 1, "health": true,
        "endpoint": "'"$model.${NAMESPACE}.svc.cluster.local"'",
        "pods": [{"name": "'"$pod"'", "ip": "'"$ip"'", "status": "up", "reason": "healthy"}]
      }
    }'
  done

手动单个同步命令：

  kubectl patch modelinstance <name> -n vc-c550-jiaofu-test --type merge -p '{
    "status": {
      "phase": "Running",
      "readyReplicas": 1,
      "totalReplicas": 1,
      "health": true,
      "endpoint": "<model>.vc-c550-jiaofu-test.svc.cluster.local",
      "pods": [{"name": "<pod-name>", "ip": "<pod-ip>", "status": "up", "reason": "healthy"}]
    }
  }'

## 4. 推理 API（scientific-model-server）

所有模型共用 FastAPI server（scientific-model-server），统一端点，ROUTE_PREFIX=scimodel：

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| /v1/scimodel/info | GET | 模型自描述（input_schema、parameter_schema、task_types） |
| /v1/scimodel/tasks | POST | 提交推理任务 |
| /v1/scimodel/tasks/{id} | GET | 查询任务状态 |
| /v1/scimodel/tasks | GET | 列出所有任务 |
| /v1/scimodel/tasks/{id}/cancel | POST | 取消任务 |
| /health | GET | 健康检查 |

公网入口经 nginx-proxy header 路由。

## 5. 注册 Instance CRD（必须手动）

模型 Deployment 运行后，仪表盘看不到。必须注册两种 CRD：

### Instance（/api/v1/instances 使用）

  apiVersion: inference.example.com/v1alpha1
  kind: Instance
  metadata:
    name: <model-name>
    namespace: vc-c550-jiaofu-test
    labels:
      app: inference-manager          // ← 必须！代码按此 label 筛选
  spec:
    template: <model-name>
    templateType: deployment
    replicas: 1
    autoScaling:
      enabled: false
    params: {}

### ModelInstance（/api/v1/model-instances 使用）

  apiVersion: inference.example.com/v1alpha1
  kind: ModelInstance
  metadata:
    name: <model-name>
    namespace: vc-c550-jiaofu-test
  spec:
    modelName: <model-name>
    template: <model-name>
    templateType: scientific-model
    cluster: metax
    namespace: vc-c550-jiaofu-test
    project: vc-c550-jiaofu-test
    path: /v1/scimodel
    endpoint: http://<model-name>:80

⚠️ ModelInstance 的 status 需要手动同步（instance-operator 不自动 reconcile ModelInstance CRD）。部署后 CRD 默认 phase="" readyReplicas=0 health=false，仪表盘显示 Pending。必须从实际 Pod 状态同步（见 §3.2）。

## 6. nginx-proxy 路由更新

每个模型部署后，在 nginx-proxy ConfigMap 的 map 块中添加路由：

  map $http_x_original_model $model_backend {
      default  "";
      "esm2"   "model-esm2.<namespace>.svc.cluster.local:8000";
  }

完整 ConfigMap 见原部署目录 `manifests/04-nginx-config.yaml`。

## 7. 模型推理测试

部署完成后验证推理是否正常。模型分两类：序列输入型和文件输入型。

### 7.1 序列输入型（可直接测，无需 AFS 数据）

| 模型 | task_type | 输入 | 注意 |
| --- | --- | --- | --- |
| ankh3 | embed | {"sequence":"MKFL..."} | — |
| deepfri | predict | {"sequence":"MKFL..."} | — |
| esm2 | embed | {"sequence":"MKFL..."} | 结果写入 AFS output_path，不直接在 API 返回 |
| evo2 | forward | {"sequence":"ATGCGT..."} | ⚠️ 必须是 DNA (ATCG)，氨基酸序列全报错 |
| proteinbert | embed | {"sequence":"MKFL..."} | — |
| protrans | embed | {"sequence":"MKFL..."} | — |

通用测试命令：

```bash
curl -X POST "http://EIP:8881/model/v1/scimodel/tasks" \
  -H "x-original-model: <model>" \
  -H "Content-Type: application/json" \
  -d '{"task_type":"embed","inputs":{"sequence":"MKFLILFNILVCLAFSYAMGKSSSS"}}'
```

### 7.2 文件输入型（需要 AFS 上的真实数据）

这些模型需要文件路径输入，不能用纯序列测试。AFS 共享存储挂载在 /data，通过 kubectl exec/ cp 可预置文件：

| 模型 | 需要 | 备注 |
| --- | --- | --- |
| alphafold3 | input_json（含 MSA） | 三轮调试到根因：缺字段名→缺 dialect/version→缺 MSA |
| boltzgen | input_yaml | 当前版本不收 sequence（历史曾收） |
| esmif1 | pdb_path | — |
| mace | train_data_path | 训练模式 |
| mattersim | script + args | — |
| mmseqs | db_path | — |
| msatransformer | msa / msa_path | 当前版本不收 sequence（历史曾收） |
| openfold | fasta_dir + alignments_dir | — |
| promptir | image_path | — |
| proteinmpnn | input_quiver | — |
| protenix | input_json | 当前版本不收 sequence（历史曾收） |
| rfantibody | target_pdb + framework_pdb | — |
| rfdiffusion | target_pdb + framework_pdb | — |
| rosettafold | input_quiver | — |

### 7.3 alphafold3 输入格式排查

递进三轮排错，完整最简（但还缺 MSA）格式：

```json
{
  "name": "test",
  "dialect": "alphafold3",
  "version": 1,
  "modelSeeds": [42],
  "sequences": [{"protein":{"id":"A","sequence":"MKFLILFNILVC"}}]
}
```

## 8. 模型专用陷阱

| 问题 | 原因 | 解决 |
| --- | --- | --- |
| 模型全部 Pending (0/1) | ModelInstance status 未同步 | 手动 patch status（见 §3.2） |
| instances API 返回 0 | CRD 缺少 label app=inference-manager | kubectl label instance <name> app=inference-manager |
| 集群页 displayName 显示 "-" | displayName 不在 cluster JSON 内 | JSON 写成 `{"displayName":"沐曦集群",...}` |
| alphafold3 推理失败 | 缺 MSA 字段 | 检查 input_json 的 sequences 格式（见 §7.3） |
| evo2 推理报错 | 用了氨基酸序列 | 必须用 DNA 序列 (ATCG) |

## 9. 压测结果

6 个序列模型，每模型 10 个任务，100% 通过：

| 模型 | 提交 | 成功 | 失败 | 平均耗时 |
| --- | --- | --- | --- | --- |
| ankh3 | 10 | 10 | 0 | 24s |
| deepfri | 10 | 10 | 0 | 24s |
| esm2 | 10 | 10 | 0 | 30s |
| evo2 | 10 | 10 | 0 | 43s |
| proteinbert | 10 | 10 | 0 | 31s |
| protrans | 10 | 10 | 0 | 28s |

## 10. 部署检查清单

  - [ ] 模板 ConfigMap 全部导入（/api/v1/templates 返回正确条数）
  - [ ] 所有模型 Deployment Running (1/1)
  - [ ] 所有模型 Service ClusterIP 分配成功
  - [ ] Instance CRD 全部创建（含 app=inference-manager label）
  - [ ] ModelInstance CRD 全部创建 + status 已同步
  - [ ] nginx-proxy ConfigMap 含所有模型的 map 规则
  - [ ] 序列模型通过 /health + 推理测试
  - [ ] 文件模型 AFS 数据就绪 + 推理测试

## 11. 队列与动态扩容

科学模型的排队链路（Redis→Kafka→dispatcher 背压→后端内部队列）与队列模式自动扩容的触发公式（第 3 个并发任务触发首次扩容）见 `references/scimodel-queue-autoscaling.md`。回答"发多少请求会扩容/怎么排队"类问题时按该文件推导，阈值须以线上 ModelPolicy 配置为准。

## 12. 新 Namespace 迁移陷阱（从老平台迁移到新 namespace）

从 `studio-ams`（老平台）迁移到新 namespace 时，会遇到三个硬编码 namespace 问题。

### 11.1 instance-operator 硬编码读模板 namespace

instance-operator 在 reconcile Instance CRD 时，**硬编码去 `studio-ams` namespace 读取模板 ConfigMap**，不读 instance-operator 自身所在的 namespace。即使 instance-operator 部署在 `vc-c550-jiaofu-test`，它仍去找 `studio-ams`。

修复方案：创建 `studio-ams` namespace + 复制所有模板 ConfigMap + 添加 RBAC 授权：

```bash
export KUBECONFIG=/Users/huron/code/ai_lab/kubeconfig_dir/config-vc-c550-jiaofu-test.yaml

# 1. 创建 studio-ams namespace
kubectl create namespace studio-ams

# 2. 从 higress-system 复制模板 ConfigMap 到 studio-ams
for cm in $(kubectl get cm -n higress-system -l inference-manager=template -o name); do
  name=$(basename $cm)
  kubectl get cm $name -n higress-system -o json | \
    jq 'del(.metadata.uid, .metadata.resourceVersion, .metadata.creationTimestamp, .metadata.managedFields) | 
        .metadata.namespace = "studio-ams"' | \
    kubectl apply -f -
done

# 3. 添加 RBAC（Role + RoleBinding，授权 instance-operator 读 studio-ams 的 ConfigMap）
kubectl apply -f deploy_platform/scientific-models/rbac-studio-ams.yaml
```

验证：instance-operator 日志中 `"Failed to get template ConfigMap"` 报错消失，Deployment/Service 正常创建。

### 11.2 ModelInstance CRD cluster 字段

ModelInstance 的 `spec.cluster` 必须与 inference-manager cluster 配置中的 cluster 名称一致。新平台用 `vc-c550-jiaofu` 而非老平台的 `metax`：

```bash
# 批量修改所有 ModelInstance 的 cluster 字段
for mi in $(kubectl get modelinstance -n vc-c550-jiaofu-test -o name); do
  name=$(basename $mi)
  kubectl patch modelinstance $name -n vc-c550-jiaofu-test --type merge \
    -p '{"spec":{"cluster":"vc-c550-jiaofu"}}'
done
```

Instance CRD 同理：
```bash
for inst in $(kubectl get instance -n vc-c550-jiaofu-test -o name); do
  name=$(basename $inst)
  kubectl patch instance $name -n vc-c550-jiaofu-test --type merge \
    -p '{"spec":{"cluster":"vc-c550-jiaofu"}}'
done
```

### 11.3 UI JS bundle 硬编码 namespace（最隐蔽）

manager-ui 的 JS bundle（`/assets/index-K-TP75DC.js`）中 **硬编码** `namespace=studio-ams`，导致：
- 概览页显示"副本总数 0，运行中 0"
- 科学模型 → 运行实例页面显示 0 条记录

**nginx sub_filter 无效**——JS 被 gzip 压缩，sub_filter 无法匹配原始文本。改用 **URL rewrite 方案**，在 manager-ui-nginx ConfigMap 中添加：

```nginx
location /api/v1/model-instances {
    # 修复 JS 硬编码 namespace=studio-ams
    if ($arg_namespace = "studio-ams") {
        rewrite ^ /api/v1/model-instances?namespace=vc-c550-jiaofu-test break;
    }
    proxy_pass http://inference-manager.higress-system.svc.cluster.local:80;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

⚠️ 注意：不要添加 `sub_filter_once off;`——nginx 不允许重复定义该指令，会导致 `nginx -t` 失败。

### 11.4 平台独立性验证

```bash
# 确认两平台 Pod 完全独立
KUBECONFIG=config-vc-c550-ai4s-sys.yaml kubectl get pods -n studio-ams | wc -l  # → 0
KUBECONFIG=config-vc-c550-jiaofu-test.yaml kubectl get pods -n vc-c550-jiaofu-test | wc -l  # → 20+
```
