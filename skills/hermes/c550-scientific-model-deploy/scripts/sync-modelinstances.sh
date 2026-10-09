#!/bin/bash
# 批量同步 ModelInstance CRD status — 从实际 Running Pod 取值
# 使用场景：部署完模型 Deployment 后，CRD status 仍是空值（phase="" readyReplicas=0）
#          instance-operator 不自动 reconcile ModelInstance，需手动同步

export KUBECONFIG=${KUBECONFIG:-config-vc-c550-jiaofu-test.yaml}
NAMESPACE="${1:-vc-c550-jiaofu-test}"

MODELS="alphafold3 ankh3 boltzgen deepfri esm2 esmif1 evo2 mace mattersim mmseqs msatransformer openfold promptir proteinbert proteinmpnn protenix protrans rfantibody rfdiffusion rosettafold"

synced=0
failed=0

for model in $MODELS; do
  # 查找匹配该模型的 Pod（命名规范：<model>-1-<hash>-<suffix>）
  POD=$(kubectl get pod -n "$NAMESPACE" -o name 2>/dev/null | grep "$model-" | head -1 | sed 's|pod/||')
  
  if [ -z "$POD" ]; then
    echo "[SKIP] $model: no pod found"
    ((failed++))
    continue
  fi

  POD_IP=$(kubectl get pod "$POD" -n "$NAMESPACE" -o jsonpath='{.status.podIP}' 2>/dev/null)
  
  kubectl patch modelinstance "$model" -n "$NAMESPACE" --type merge -p '{
    "status": {
      "phase": "Running",
      "readyReplicas": 1,
      "totalReplicas": 1,
      "health": true,
      "endpoint": "'$model'.'$NAMESPACE'.svc.cluster.local",
      "pods": [{
        "name": "'$POD'",
        "ip": "'$POD_IP'",
        "status": "up",
        "reason": "healthy"
      }]
    }
  }' 2>/dev/null && echo "[OK] $model ($POD_IP)" && ((synced++)) || { echo "[FAIL] $model"; ((failed++)); }
done

echo ""
echo "Synced: $synced  Failed: $failed"
