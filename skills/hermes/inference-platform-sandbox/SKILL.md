---
name: inference-platform-sandbox
description: Configure, debug, or validate Sandbox integration on the current heterogeneous inference platform. Use for H Brainbox and TongSuan OpenSandbox resource pools, sandbox-pool-config, sandbox-server, environment/instance APIs, file upload/download, volumes, projectId or AK/SK mismatches, 403/500 errors, SWE-rollout gateway validation, or gateway-vs-native sandbox behavior.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [sandbox, inference-platform, gateway, brainbox, tongsuan, validation]
    related_skills: [swe-image-delivery, openswe-runtime-builder]
---

# Inference Platform Sandbox

Use this skill for Sandbox gateway work on the current heterogeneous platform. Environment values (gateway URL, SSH, resource pools, image tags) are **mutable configuration** and live in [references/platform-env-pjlab.md](references/platform-env-pjlab.md); read that reference first and re-verify against the live platform.

For TongSuan native OpenSandbox semantics, also use the `tongsuan-opensandbox-*` skills. This skill only needs the TongSuan subset that the SWE workflow actually uses; do not bulk-migrate or bulk-load TongSuan skills merely because a cross-reference exists.

## Architecture

- Management APIs use `inference-manager`.
- Execd/file APIs use `sandbox-server` through nginx route `/v1/sandboxes/{id}/proxy/{port}`.
- `inference-manager` reads pool settings from `sandbox-pool-config` ConfigMap and hot-refreshes in about 60 seconds.
- The current `sandbox-server` rollout intentionally keeps `SANDBOX_POOL_CONFIG` in deployment env. Do not refactor that into a Secret/ConfigMap unless the user explicitly asks.

## Supported Sandbox Features

- Sandbox environment create/list/get/delete through `/api/v1/sandbox-environments`.
- Environment APIs return `swepro-*` environments so SWE gateway clients can reuse them; the UI hides `swepro-*` by default and can show them through keyword search.
- Sandbox instance create/list/get/delete/renew through `/api/v1/sandboxes`.
- SDK-compatible `/v1/sandboxes` management routes.
- Execd proxy through `/v1/sandboxes/{id}/proxy/44772`.
- Streaming command output.
- Multipart file upload and file download through the proxy route.
- SDK multipart upload metadata with numeric `mode` is normalized for Brainbox compatibility.
- `volumes` passthrough in environment/sandbox creation requests.
- Empty `resource` routes to TongSuan OpenSandbox. Explicit `resource=brainbox` routes to H Brainbox.
- OpenSandbox creation without `environmentId` directly creates a sandbox. H Brainbox keeps the shared-environment compatibility path.
- `/api/v1/sandboxes` without `environmentId` lists TongSuan project sandboxes for the default pool; H Brainbox without `environmentId` returns HTTP 200 with an empty list.

## Authentication

Resolve the gateway admin password from runtime secret storage, environment variables, or explicit user input at execution time. Never write it into files, logs, or shell profiles; fail closed if it is absent.

Management API:

```bash
TOKEN=$(GATEWAY_ADMIN_PASSWORD=$GATEWAY_ADMIN_PASSWORD curl -s -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\": \"$GATEWAY_ADMIN_PASSWORD\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("token",""))')
```

Use `Authorization: Bearer *** for `/api/v1/*`.

Data-plane proxy calls require:

- `OPEN-SANDBOX-API-KEY: $TOKEN`
- `X-Sandbox-Access-Token: <accessToken from Running sandbox detail>`
- `X-Sandbox-Resource: <resource id>` whenever the caller selected a resource explicitly, including `brainbox`

Do not reuse a static SAT across sandboxes.

## Common Checks

Get host, kubeconfig, namespace, and pool names from `references/platform-env-pjlab.md`, then:

```bash
ssh -i <operator-ssh-key> -p <port> root@<host> \
  'kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml -n inference-ng get deploy,pods,svc -o wide'

ssh -i <operator-ssh-key> -p <port> root@<host> \
  'kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml -n inference-ng get cm sandbox-pool-config -o yaml'

ssh -i <operator-ssh-key> -p <port> root@<host> \
  'kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml -n inference-ng logs deploy/inference-manager --tail=50 | grep "Loaded sandbox pool"'
```

List environments:

```bash
curl -s "$BASE/api/v1/sandbox-environments?page=1&pageSize=5" \
  -H "Authorization: Bearer *** | python3 -m json.tool
```

Verify empty sandbox list compatibility:

```bash
curl -s "$BASE/api/v1/sandboxes?page=1&pageSize=20" \
  -H "Authorization: Bearer *** | python3 -m json.tool
```

Expected: HTTP 200 with `items: []`.

Run full smoke:

```bash
cd <inference-gateway-sd repo>
BASE=http://<gateway-host>:<gateway-port> WAIT_SECONDS=300 \
  inference-manager/scripts/sandbox_smoke_test.sh

BASE=http://<gateway-host>:<gateway-port> \
SANDBOX_RESOURCE=brainbox \
WAIT_SECONDS=300 \
  inference-manager/scripts/sandbox_smoke_test.sh

BASE=http://<gateway-host>:<gateway-port> \
SANDBOX_RESOURCE='<tongsuan-resource-id>' \
WAIT_SECONDS=300 \
  inference-manager/scripts/sandbox_smoke_test.sh
```

## SWE-rollout Validation

Use gateway mode against the SWE-rollout project directory named in `references/platform-env-pjlab.md`:

```bash
OPEN_SANDBOX_GATEWAY_TOKEN=$OPEN_SANDBOX_GATEWAY_TOKEN ./scripts/brainbox.sh --platform gateway validate base
OPEN_SANDBOX_GATEWAY_TOKEN=$OPEN_SANDBOX_GATEWAY_TOKEN ./scripts/brainbox.sh --platform gateway smoke gold --apply
OPEN_SANDBOX_GATEWAY_TOKEN=$OPEN_SANDBOX_GATEWAY_TOKEN ./scripts/brainbox.sh --platform gateway smoke noop --apply
```

Task image prefix and gateway image map order are in `references/platform-env-pjlab.md`.

## Fast Triage

- `403: project permission denied`: AK/SK and `projectId` do not match, or the project is not authorized.
- `500: Failed to list environments`: Brainbox unreachable, stale config, or invalid pool config.
- `500: Failed to list sandboxes`: should be fixed; verify the deployed manager image and test `/api/v1/sandboxes?page=1&pageSize=20`.
- data-plane `401`: sandbox is not Running, SAT is stale, or the proxy call missed `X-Sandbox-Access-Token`.
- upload failure: verify nginx route, `sandbox-server` readiness, multipart fields `metadata` and `file`, and the 100 MiB nginx upload limit.

## Authorization and Cleanup

Read-only checks (listing environments/sandboxes, logs, ConfigMap reads, smoke tests that create no persistent state) may proceed without extra authorization. Creating sandboxes for validation is fine, but **deleting temporary sandboxes after validation is expected**. Any change to platform deployment, pool config, or gateway configuration requires explicit user authorization first.

Never print or copy AK/SK, gateway admin password, or SAT values into output, logs, or files.
