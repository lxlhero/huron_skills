---
name: dev-team-tester
description: Test engineering agent (DEPRECATED — split into test-writer + test-runner). Now delegates to dev-team-test-writer for test authoring and dev-team-test-runner for execution and reporting. Maintained for backward compatibility; orchestrator should call the split agents directly.
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [testing, qa, dev-team, deprecated, agent]
    related_skills: [dev-team-test-writer, dev-team-test-runner, dev-team-orchestrator]
    domain: quality
    role: specialist
---

# DevTeam Test Agent (v2.0 — 拆分为二)

此 skill 已拆分。请直接调度两个新 agent：

## 新架构

| Agent | 职责 | 何时调用 |
|-------|------|---------|
| **dev-team-test-writer** | 读取代码 → 编写测试 | test phase 前半段 |
| **dev-team-test-runner** | 运行测试 → 分类错误 → 出报告 | test phase 后半段 |

## 旧版兼容

如果需要合并调用（不推荐），依次加载两个 skill：
1. Load `dev-team-test-writer` → 编写测试
2. Load `dev-team-test-runner` → 执行测试

orchestrator 已更新为直接分别调度两个 agent。
