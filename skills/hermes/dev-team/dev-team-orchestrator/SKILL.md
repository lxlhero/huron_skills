---
name: dev-team-orchestrator
description: "DevTeam master controller. Five commands: devteam build [需求文件|文件夹] (create from scratch, optional requirements doc), devteam debug (fix bugs), devteam add (add features), devteam deploy (build image and deploy), devteam sync (sync skills to repo). Coordinates 11 specialized agents. Auto-syncs skills to huron_skills repo."
version: 2.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [orchestrator, multi-agent, devteam, build, debug, add, deploy, requirements, sync]
    related_skills: [dev-team-pm, dev-team-architect, dev-team-backend, dev-team-frontend, dev-team-tester, dev-team-reviewer, dev-team-logging, dev-team-debugger, dev-team-devops, dev-team-deploy]
    domain: workflow
    role: architect
---

# DevTeam Orchestrator v2.1

DevTeam 总指挥。五个命令入口 + 需求文件输入 + 自动同步。

## 命令入口

| 命令 | 触发词 | 用途 |
|------|--------|------|
| `devteam build [需求文件\|文件夹]` | "devteam build", "build me", "创建", "搭建" | 从零搭建新项目。可选传入需求文档 |
| `devteam add` | "devteam add", "add feature", "加功能", "新增" | 给已有项目加功能 |
| `devteam debug` | "devteam debug", "debug", "修bug", "报错", "定位" | 定位修复 bug |
| `devteam deploy` | "devteam deploy", "deploy", "部署", "打镜像" | 打镜像部署服务 |
| `devteam sync` | "devteam sync", "同步skills" | 手动同步 ~/.hermes/skills/dev-team/ → huron_skills |

## DevTeam Agent 名单 (11人)

| Agent | 职责 |
|-------|------|
| PM | 需求澄清，规格说明书。**支持读取外部需求文档** |
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

触发: 用户说 "devteam build <描述>" [<需求文件|文件夹>] ["--dir <目录>"]

### Phase 0: 开工
1. 解析用户输入，提取：
   - 项目描述（"一个博客系统"）
   - 目标目录（"放在 ~/projects/blog"）
   - **需求文件/文件夹路径**（"用 /path/to/requirements.md"）
2. 如果用户没指定目录，问用户
3. `mkdir -p <path> && git init && mkdir -p specs backend frontend`

### Phase 0.5: 读取需求（如果提供了需求文件/文件夹）
**仅当用户指定了需求源时执行。**

1. 如果是文件路径 → read_file 读取全文
2. 如果是文件夹路径 → search_files 列出所有文件，逐个 read_file 读取
3. 支持格式：.md, .txt, .yaml, .json, .toml
4. 将读取的内容保存为 `<project>/specs/requirements-source/` 副本（供后续参考）
5. 提炼需求要点摘要，传给 Phase 1 PM

### Phase 1: PM
Load `dev-team-pm` → delegate_task，context 必须包含：
- 用户原始描述
- **需求文件关键内容**（如果有 Phase 0.5 产出）
- 目标目录

PM 产出 specs/feature.spec.md（EARS 格式需求规格书）

### Phase 2: Architect
Load `dev-team-architect` → 系统设计 → specs/architecture.md
context 必须包含 specs/feature.spec.md 路径 + Phase 0.5 需求摘要

### Phase 3: Plan
Load `writing-plans` → 拆成 bite-sized 任务清单

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

### Phase 10: 同步 Skill（自动）
完成构建后自动执行 `devteam sync`，将更新的 skill 同步到 huron_skills 仓库。

---

## devteam add — 增量加功能

触发: "devteam add <功能>" 或 "给我加个 <功能>"

1. 确认项目路径 + 要加的功能
2. Load `dev-team-pm` → 澄清增量需求
3. Load `writing-plans` → 拆解增量任务
4. dispatch Backend/Frontend 逐个实现
5. Test → Review → git commit
6. 自动执行 `devteam sync`

---

## devteam debug — 定位修bug

触发: "devteam debug <bug>" 或 "帮我看看这个报错"

1. 确认项目路径 + bug 描述/报错
2. Load `dev-team-debugger` → dispatch:
   Reproduce → Isolate → Hypothesize → Fix → Prevent
3. Test → Review → git commit
4. 自动执行 `devteam sync`

---

## devteam deploy — 打镜像部署

触发: "devteam deploy" 或 "部署" 或 "打镜像"

1. 确认项目路径
2. Load `dev-team-deploy` → dispatch:
   Build → Test locally → Push → Deploy → Verify
3. 自动执行 `devteam sync`

---

## devteam sync — 同步 Skill 到 huron_skills

触发: "devteam sync" 或 "同步skills"

执行步骤:
1. `cp -r ~/.hermes/skills/dev-team/* /Users/huron/code/ai_lab/huron_skills/skills/hermes/dev-team/`
2. 检查 README.md 是否需要更新（如果新增/修改了命令或功能）
3. `cd /Users/huron/code/ai_lab/huron_skills && git add skills/hermes/dev-team/ && git commit -m "devteam: sync skills [简要说明]" && git push`
4. 报告同步状态

**build/add/debug/deploy 最后一步自动执行 sync。**

---

## 调度规范

每次 `delegate_task` 必须包含:
```
PROJECT PATH: /absolute/path
TECH STACK: <backend + frontend + db>
TASK: <具体任务>
CONSTRAINTS: <特殊要求>
RELATED FILES: <Phase 0.5 需求文件路径列表>
```

## 需求文件格式

支持的输入格式:

### 单文件
```
devteam build ~/requirements/blog-v1.md --dir ~/projects/blog
```
需求文件可以是:
- Markdown 产品需求文档 (PRD)
- 纯文本功能列表
- YAML/JSON 结构化需求
- TOML 配置文件

### 文件夹
```
devteam build ~/requirements/blog/ --dir ~/projects/blog
```
文件夹内应有多个 .md 文件，PM 会逐个读取分析。

### 需求文件模板示例
```markdown
# 项目名称
## 背景
简要描述为什么做这个项目
## 功能需求
### F1: 用户系统
- 注册（email + 密码）
- 登录（JWT）
- 个人设置
### F2: 核心功能
- 创建文章
- 编辑文章
- 删除文章
## 非功能需求
- 响应时间 < 200ms
- 支持 1000 并发
## 技术约束
- 必须用 PostgreSQL
- 必须部署到 K8s
## UI 要求
- 风格：苹果设计语言
- 响应式，支持移动端
```

PM 会据此生成 EARS 格式的正式规格书。

---

## 铁律
- 先建目录再派 Agent
- Load agent skill BEFORE dispatch
- delegate_task context 必须完整（子 Agent 无记忆）
- 每 phase git commit
- Critical issue 不解决不进下一 phase
- 不同文件的 Agent 可并行，同文件必须串行
- **build/add/debug/deploy 完成后自动执行 sync → huron_skills**
- 如果用户提供了需求文件，Phase 0.5 必须先读
