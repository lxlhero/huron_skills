---
name: c550-inference-platform-deploy
description: "C550 K8s 推理平台完整部署技能。涵盖基础设施部署、公网访问架构(EIP-DNAT-跳板机nginx-K8s)、模型部署与CRD注册、常见陷阱(OVN慢分配、Pod IP vs Service IP、namespace不一致)及验证清单。"
version: 2.0.0
metadata:
  hermes:
    tags: [devops, mlops, k8s, inference, c550, deployment]
---

# C550 推理平台部署

## 概述

在 C550 K8s 集群上部署完整 AI4S 推理平台。平台 = 5 个基础设施组件 + N 个科学模型 Deployment，通过跳板机 nginx 对外暴露公网访问。

核心架构链路：

```
公网 → EIP:8881 → DNAT → 跳板机 nginx:88 → K8s Pod IP（直连）
                                              ├─ /api/v1/* → inference-manager
                                              ├─ /model/*  → nginx-proxy
                                              └─ /         → UI SPA
```

## 1. 集群信息

| 项目 | 值 |
|------|---|
| 集群 | C550 vcluster (vc-c550-jiaofu-test) |
| kubeconfig | config-vc-c550-jiaofu-test.yaml |
| API Server | https://10.140.158.130:33434 |
| CoreDNS | 10.110.103.45 |
| 镜像仓库 | registry2.d.pjlab.org.cn |
| 镜像拉取 secret | image-pull-secret |
| CNI | OVN（初次分配 IP 很慢，几分钟到十几分钟） |
| StorageClass | quark-vcproxy-sc |
| 跳板机 | 10.120.17.201 (ssh root@10.140.158.130 -p 49170) |

## 2. 基础设施部署

5 个组件，按顺序部署，每个 Running 后再下一个：

1. instance-operator（Deployment + RBAC）
2. inference-manager（Deployment + ConfigMap + RBAC）
3. inference-manager-ui（Deployment + NodePort Service）
4. nginx-proxy（Deployment + ConfigMap + ClusterIP Service）
5. gateway-nginx（可选，NodePort 辅助代理）

部署命令：

  export KUBECONFIG=.../config-vc-c550-jiaofu-test.yaml
  kubectl apply -f manifests/<component>.yaml
  kubectl -n vc-c550-jiaofu-test get pods -w

## 3. 公网访问架构

### 3.1 链路

EIP 10.140.158.130:8881 → 商汤 DNAT → 跳板机 10.120.17.201:88 (nginx) → Pod IP 直连

### 3.2 跳板机网络限制

跳板机在 Pod 子网 10.120.16.0/20 上：
  - Pod IP (10.120.x.x): 可达 ✓
  - Node IP (10.12.x.x): 不可达 ✗
  - Service ClusterIP (10.100.x.x): 不可达 ✗

因此 nginx 必须使用 Pod IP 直连，不能用 Service ClusterIP 或 NodePort。

### 3.3 跳板机 nginx 配置

完整可用的生产配置见 `references/nginx-bastion.conf`。关键要点：

  server {
      listen 88;
      client_max_body_size 100m;

      // 所有管理 API → inference-manager，硬编码 namespace
      location /api/v1/ {
          proxy_pass http://<inference-manager-pod-ip>:8080$uri?namespace=vc-c550-jiaofu-test;
          proxy_set_header Host $host;
          proxy_read_timeout 120s;
          proxy_buffering off;
      }

      // 模型推理网关
      location /model/ {
          proxy_pass http://<nginx-proxy-pod-ip>/;
          proxy_set_header Host $host;
          proxy_pass_request_headers on;
          proxy_read_timeout 600s;
      }

      // SPA 静态资源
      location / { ... }
      location /assets/ { ... }
  }

### 3.4 注意事项

  - Pod IP 重启会变，需同步更新 nginx 配置
  - proxy_pass 不能用 nginx 变量（变量需要 resolver，但 IP 不需要）
  - 不能跳板机内 curl Service ClusterIP 验证（不可达），用 Pod IP 验证

## 4.1 首次部署数据初始化

新集群 inference-manager 启动后，Cluster、Template、ModelInstance 三类数据全部为空，需手动初始化。

### Cluster ConfigMap

  kubectl create configmap inference-manager-cluster-metax \
    -n vc-c550-jiaofu-test \
    --from-literal=endpoint=10.140.158.130:38080 \
    --from-literal=dnat=10.140.158.130:38080 \
    --from-literal=type=ip \
    --from-literal=status=active \
    --from-literal=cluster='{"displayName":"沐曦集群","clusterType":"ip","DNAT":"10.140.158.130:38080","externalService":"metax-external","grafanaDatasourceUid":"P25CDD04CF7FBA6B1"}'
  kubectl label configmap inference-manager-cluster-metax -n vc-c550-jiaofu-test inference-manager=cluster

⚠️ displayName 必须在 cluster JSON 内，不能作为独立 data key，否则 API 显示 "-"。

### Template ConfigMaps（从旧集群迁移）

模板存储为 ConfigMap，label inference-manager=template，name 格式 inference-manager-template-<model>。从旧集群 studio-ams 导出到新集群 vc-c550-jiaofu-test：

  for model in alphafold3 ankh3 ...; do
    cm="inference-manager-template-${model}"
    KUBECONFIG=$OLD kubectl get cm $cm -n studio-ams -o json | \
      jq 'del(.metadata.uid,.metadata.resourceVersion,.metadata.creationTimestamp,.metadata.managedFields) |
          .metadata.namespace="vc-c550-jiaofu-test"' | \
      KUBECONFIG=$NEW kubectl apply -f -
  done

### ModelInstance CRD 批量状态同步

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

每个模型 = 1 个 Deployment + 1 个 Service（ClusterIP）：

  image: registry2.d.pjlab.org.cn/ai4s/scientific-model-server:v2.0.0
  env: MODEL_NAME=<name>
  port: 8000
  volumeMounts: /mnt/afs (AFS 共享存储)

### 4.2 推理 API（scientific-model-server）

所有模型共用 FastAPI server（scientific-model-server），统一端点，ROUTE_PREFIX=scimodel：

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| /v1/scimodel/info | GET | 模型自描述（input_schema、parameter_schema、task_types） |
| /v1/scimodel/tasks | POST | 提交推理任务 |
| /v1/scimodel/tasks/{id} | GET | 查询任务状态 |
| /v1/scimodel/tasks | GET | 列出所有任务 |
| /v1/scimodel/tasks/{id}/cancel | POST | 取消任务 |
| /health | GET | 健康检查 |

公网入口（经 nginx-proxy header...[truncated]

### 4.3 注册 Instance CRD（必须手动）

模型 Deployment 运行后，仪表盘看不到。必须注册两种 CRD：

Instance（/api/v1/instances 使用）：

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

ModelInstance（/api/v1/model-instances 使用）：

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

⚠️ ModelInstance 的 status 需要手动同步（instance-operator 不自动 reconcile ModelInstance CRD）。部署后 CRD 默认 phase="" readyReplicas=0 health=false，仪表盘显示 Pending。必须从实际 Pod 状态同步。

批量同步脚本见 `scripts/sync-modelinstances.sh`。手动单个同步命令：

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

## 4.5 模板导入（从旧集群迁移）

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

在 nginx-proxy ConfigMap 的 map 块中添加：

  map $http_x_original_model $model_backend {
      default  "";
      "esm2"   "model-esm2.<namespace>.svc.cluster.local:8000";
  }

## 5. nginx-proxy 铁律

1. worker_processes 固定为 4（节点 256 核，auto 会导致 reload 时 OOM）
2. upstream 必须用 FQDN（nginx 不解析短名）
3. resolver 指向 CoreDNS IP（10.110.103.45）
4. 缺失 x-original-model header 返回 400 而非 502
5. ConfigMap data key 必须是 nginx.conf
6. 内存限制 512Mi

## 6. Namespace 陷阱

inference-manager 两个接口的默认 namespace 与部署 namespace 不一致：

| 接口 | 默认 namespace | 原因 |
| --- | --- | --- |
| /api/v1/model-instances | "studio-ams" | Go 代码硬编码 |
| /api/v1/instances | "default" | admin 用户 project="" 的 fallback |

临时方案：跳板机 nginx 丢弃客户端 query string，硬编码 ?namespace=vc-c550-jiaofu-test。
长期方案：改 inference-manager 源码使 namespace 可通过环境变量配置。

## 7. OVN CNI 应对

  - 新 Pod IP 分配很慢（几分钟到十几分钟），但最终成功
  - 症状链：Pending → "no address allocated" → "route is not ready" → Running
  - 不要重复创建/删除 Pod，等待即可
  - hostNetwork 被 Kyverno 拦截
  - 判断 OVN 是否可用的方法：观察旧 Pending Pod 是否最终变 Running

## 8. 常见陷阱速查

| 问题 | 原因 | 解决 |
| --- | --- | --- |
| 仪表盘 No data | namespace 不对或未注册 CRD | 用正确 namespace 测试 API，创建 Instance/ModelInstance CRD |
| 模型全部 Pending (0/1) | ModelInstance status 未同步 | 手动 patch status 从实际 Running Pod 取值 |
| 集群页 displayName 显示 "-" | displayName 在 cluster JSON 字段里而非独立 data key | JSON 写成 `{"displayName":"沐曦集群","clusterType":"ip",...}` |
| instances API 返回 0 | CRD 缺少 label app=inference-manager | kubectl label instance <name> app=inference-manager |
| instances API 403 | RBAC 不足 | 创建 ClusterRole 授予 instances CRD 的 get/list/watch 权限 |
| nginx 404 全部 API | proxy_pass 用了变量且无 resolver | 直接硬编码 IP |
| Pod 卡 PodInitializing | OVN 慢分配 | 等待，不重复操作 |
| 跳板机超时 | 访问了 Service ClusterIP | 改用 Pod IP |
| 浏览器白屏/转圈 | API 返回 HTML 而非 JSON（nginx 未匹配 /api/v1/ 通配） | nginx 用 `location /api/v1/` 通配所有 API 路径 |

## 10. 数据存储架构

inference-manager 从 K8s ConfigMap 读取所有配置数据，不依赖外部数据库。

| 页面 | 存储 | Label | 命名规范 | key 格式 |
| --- | --- | --- | --- | --- |
| 集群管理 | ConfigMap | inference-manager=cluster | inference-manager-cluster-<name> | cluster JSON |
| 模板管理 | ConfigMap | inference-manager=template | inference-manager-template-<name> | 模板内容 |
| 路由管理 | ConfigMap | inference-manager=route | inference-manager-route-<project>-<name> | route JSON |
| 运行实例 | ModelInstance CRD | — | <model-name> | spec + status |

### Cluster ConfigMap 的 cluster JSON 格式

代码按 ClusterConfigJSON 结构解析 ConfigMap data 中的 "cluster" key：

    {
      "displayName": "沐曦集群",
      "clusterType": "ip",
      "DNAT": "10.140.158.130:38080",
      "externalService": "metax-external",
      "grafanaDatasourceUid": "P25CDD04CF7FBA6B1"
    }

⚠️ displayName 必须在 cluster JSON 内，不能作为独立 data key。否则 API 返回 displayName 为 "-"。

### 路由管理说明

路由管理 /api/v1/routes 是给 LLM 模型用的（配置 API Key 限流等），科学模型推理不走这个。科学模型的请求链路：

    客户端 → POST /model/ (+ x-original-model header)
      → gateway-nginx 转发到 nginx-proxy
      → nginx-proxy map $http_x_original_model 查 upstream
      → 直接代理到模型 Pod 的 8000 端口

科学模型在平台上**不需要创建路由**。旧平台 4 条路由全为 LLM（deepseek/glm/minimax/qwen），21 个科学模型一条路由都没有。

## 11. 验证清单

  - [ ] 5 个基础设施组件全部 Running
  - [ ] http://EIP:8881 可访问
  - [ ] 登录 admin/admin123 成功
  - [ ] 仪表盘显示模型数量和列表
  - [ ] /api/v1/instances 返回 20 条
  - [ ] /api/v1/model-instances 返回 20 条
  - [ ] /api/v1/clusters 返回 200
  - [ ] /api/v1/templates 返回 200
  - [ ] 各模型 /health 返回 200
  - [ ] 通过 nginx-proxy 推理正常


## 9. 当前部署状态（v2.0 截止点）

⚠️ 部署尚未完成——LLM 推理和 Sandbox 还没接进来。

### 已完成
- inference-manager + UI：部署正常，公网 http://10.140.158.130:8881
- 20 个科学模型 Deployment：全部 Running (1/1)
- 管理面数据：Cluster / Template / Instance / ModelInstance 全部初始化
- 公网入口：EIP → DNAT → 跳板机 nginx 链路通畅
- 6 个序列模型推理验证通过（ankh3, deepfri, esm2, evo2, proteinbert, protrans）
- 其余 14 个模型 Pod healthy（缺少 AFS 测试数据）

### 未完成
1. LLM 推理：未部署 deepseek / glm / qwen 等。部署后需创建 Route ConfigMap + ModelInstance CRD
2. Sandbox：交互式编程环境未部署
3. 文件模型测试数据：14 个模型需要 PDB / MSA / input_json 等文件
4. 前端硬编码：JS bundle 含旧平台地址，需重建 UI 镜像

### 接手关键词
| 资源 | 路径/地址 |
| --- | --- |
| 部署报告 | /Users/huron/code/ai_lab/deploy_inference_platform/C550推理平台部署报告.md |
| Kubeconfig | /Users/huron/code/ai_lab/kubeconfig_dir/config-vc-c550-jiaofu-test.yaml |
| 推理网关源码 | /Users/huron/code/ai_lab/inference-gateway/ |
| 跳板机 SSH | ssh -p 49170 root@10.140.158.130 |
| DNAT 控制台 | console.d.pjlab.org.cn（IAM: ailabdev / liangxiuliang）

## 12. 模型推理测试与压测

部署完成后验证推理是否正常。模型分两类：序列输入型和文件输入型。

### 12.1 序列输入型（可直接测，无需 AFS 数据）

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

### 12.2 文件输入型（需要 AFS 上的真实数据）

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

### 12.3 alphafold3 输入格式排查

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

### 12.4 压测结果

6 个序列模型，每模型 10 个任务，100% 通过（详见 references/model-pressure-test.md）：

| 模型 | 提交 | 成功 | 失败 | 平均耗时 |
| --- | --- | --- | --- | --- |
| ankh3 | 10 | 10 | 0 | 24s |
| deepfri | 10 | 10 | 0 | 24s |
| esm2 | 10 | 10 | 0 | 30s |
| evo2 | 10 | 10 | 0 | 43s |
| proteinbert | 10 | 10 | 0 | 31s |
| protrans | 10 | 10 | 0 | 28s |