---
name: dev-team-orchestrator
description: "DevTeam master controller. Four commands: devteam build (create from scratch), devteam debug (fix bugs), devteam add (add features), devteam deploy (build image and deploy). Coordinates 11 specialized agents."
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [orchestrator, multi-agent, devteam, build, debug, add, deploy]
    related_skills: [dev-team-pm, dev-team-architect, dev-team-backend, dev-team-frontend, dev-team-tester, dev-team-reviewer, dev-team-logging, dev-team-debugger, dev-team-devops, dev-team-deploy]
    domain: workflow
    role: architect
---

# DevTeam Orchestrator v2.0

DevTeam 总指挥。四个命令入口，11 个专业 Agent。

## 命令入口

| 命令 | 触发词 | 用途 |
|------|--------|------|
| `devteam build` | "devteam build", "build me", "创建", "搭建" | 从零搭建新项目 |
| `devteam add` | "devteam add", "add feature", "加功能", "新增" | 给已有项目加功能 |
| `devteam debug` | "devteam debug", "debug", "修bug", "报错", "定位" | 定位修复 bug |
| `devteam deploy` | "devteam deploy", "deploy", "部署", "打镜像" | 打镜像部署服务 |

## DevTeam Agent 名单 (11人)

| Agent | 职责 |
|-------|------|
| PM | 需求澄清，规格说明书 |
| Architect | 系统设计，架构图，技术选型 |
| Backend | FastAPI/Python API 开发 |
| Frontend | React/Vue 前端开发 |
| Tester | 测试编写+执行 |
| Reviewer | 代码审查+安全检查 |
| Logging | 结构化日志+监控 |
| Debugger | 根因分析+修复 |
| DevOps | Dockerfile+CI/CD 配置 |
| Deploy | 打镜像+推送+部署 |

---

## devteam build — 从零搭建项目

触发: 用户说 "devteam build <描述>" 或 "build me <描述>"

### Phase 0: 开工
1. 问用户：放哪个目录？
2. `mkdir -p <path> && git init && mkdir -p specs backend frontend`

### Phase 1: PM
Load `dev-team-pm` → 澄清需求 → 写 specs/feature.spec.md

### Phase 2: Architect
Load `dev-team-architect` → 系统设计 → specs/architecture.md

### Phase 3: Plan
Load `writing-plans` → 拆成 bite-sized 任务

### Phase 4: 实现
按任务 dispatch:
- Backend → `delegate_task` + dev-team-backend context
- Frontend → `delegate_task` + dev-team-frontend context
不同文件的 Backend/Frontend 可并行

### Phase 5: Test
Load `dev-team-tester` → delegate_task

### Phase 6: Review
Load `dev-team-reviewer` → delegate_task
Critical issues → 回 Phase 4 → 重新 Review

### Phase 7: Logging
Load `dev-team-logging` → delegate_task

### Phase 8: DevOps
Load `dev-team-devops` → delegate_task

### Phase 9: 验证
pytest -v + curl /api/health + git commit

---

## devteam add — 增量加功能

触发: "devteam add <功能>" 或 "给我加个 <功能>"

1. 确认项目路径 + 要加的功能
2. Load `dev-team-pm` → 澄清增量需求
3. Load `writing-plans` → 拆解增量任务
4. dispatch Backend/Frontend 逐个实现
5. Test → Review → git commit

---

## devteam debug — 定位修bug

触发: "devteam debug <bug>" 或 "帮我看看这个报错"

1. 确认项目路径 + bug 描述/报错
2. Load `dev-team-debugger` → dispatch:
   Reproduce → Isolate → Hypothesize → Fix → Prevent
3. Test → Review → git commit

---

## devteam deploy — 打镜像部署

触发: "devteam deploy" 或 "部署" 或 "打镜像"

1. 确认项目路径
2. Load `dev-team-deploy` → dispatch:
   Build → Test locally → Push → Deploy → Verify

---

## 调度规范

每次 `delegate_task` 必须包含:
```
PROJECT PATH: /absolute/path
TECH STACK: <backend + frontend + db>
TASK: <具体任务>
CONSTRAINTS: <特殊要求>
```

## 铁律
- 先建目录再派 Agent
- Load agent skill BEFORE dispatch
- delegate_task context 必须完整（子 Agent 无记忆）
- 每 phase git commit
- Critical issue 不解决不进下一 phase
- 不同文件的 Agent 可并行，同文件必须串行
