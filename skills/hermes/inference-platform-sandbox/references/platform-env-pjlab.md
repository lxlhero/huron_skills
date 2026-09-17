# Platform Environment: PJLab (ECS-louwenjie)

This reference holds the current PJLab environment values for `inference-platform-sandbox`. All values here are **mutable configuration**, not skill defaults. Verify against the live platform before relying on them; they change with redeployments.

Do not duplicate these values in the main `SKILL.md`. Do not add credentials here.

## Host and Kubernetes

- host: `ecs-louwenjie`
- SSH: `ssh root@10.12.111.133 -p 35208` (use the operator machine's existing SSH key; the skill does not ship keys or passwords)
- Kubernetes: single-node `k3s`
- server kubeconfig: `/etc/rancher/k3s/k3s.yaml`
- namespace: `inference-ng`

## Services

- external gateway URL: `http://10.12.111.133:10018`
- sandbox environments UI: `http://10.12.111.133:10018/sandboxes/environments`
- manager service: `inference-manager`
- data-plane proxy service: `sandbox-server`
- source repo: `/Users/huron/code/ai_lab/inference-gateway-sd`
- ECS deploy overlay: `/Users/huron/code/ai_lab/inference-gateway-sd/deploy/deploy_ecs_louwenjie_20260831`

Current validated images (recheck before use):

- `inference-manager`: `registry2.d.pjlab.org.cn/ccr-inference/inference-manager:ng-20260901-brainbox-resource-v1`
- `inference-manager-ui`: `registry2.d.pjlab.org.cn/ccr-inference/inference-manager-ui:ng-20260901-tongsuan-default-direct-v1`
- `sandbox-server`: `registry2.d.pjlab.org.cn/ccr-inference/sandbox-server:ng-20260901-brainbox-resource-v1`
- `nginx-proxy`: `registry2.d.pjlab.org.cn/ccr-inference/nginx:1.27`

## Resource Pools

- `10.12.111.143/ailab-ma4agismall`: TongSuan OpenSandbox default pool, type `opensandbox`, server `http://10.12.111.143`, project `ailab-ma4agismall`, label `通算平台 Sandbox`.
- `brainbox`: H Brainbox pool, type `brainbox`, server `https://h.pjlab.org.cn`, project `ailab-ma4tool`, label `H 集群 Brainbox`; explicit `resource=brainbox` selects H even though TongSuan is default.

Both pools currently have credentials configured in the platform pool config and have passed end-to-end gateway smoke tests. Credentials live only in the platform pool config; never print or copy AK/SK values.

## SWE-rollout Validation Project

- project directory: `/Users/huron/code/ai_lab/sandbox_dir/SWE-rollout-pipeline-fsy-dev`
- task images must use the `registry-v2.h.pjlab.org.cn/ailab/swe-bench_pro` prefix
- gateway image map order: `<task.toml source image>\t<registry-v2 platform image>`
- for 10-task validation, prefer a separate `swebenchpro-base-10.tsv` map instead of overwriting the full map

## User Docs

- General Sandbox docs: `/Users/huron/code/ai_lab/sandbox_dir/异构平台 Sandbox 使用文档.md`
- SWE-rollout guide: `/Users/huron/code/ai_lab/sandbox_dir/SWE-rollout-pipeline-fsy-dev-异构平台验证指南.md`

## Historical Note

Do not use old `config-audit` or `vc-llm-audit-ng` settings for current checks unless the user explicitly asks for historical comparison.
