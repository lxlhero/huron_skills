---
name: dev-team-orchestrator
description: "DevTeam master controller. Five commands: devteam build [需求文件|文件夹] (create from scratch with optional requirements doc), devteam debug (fix bugs), devteam add (add features), devteam deploy (build image and deploy), devteam sync (sync skills to repo). Coordinates 11 specialized agents. Auto-syncs skills to huron_skills repo."
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
| `devteam build [需求文件\|文件夹]` | "devteam build", "build me", "创建", "搭建" | 从零搭建。可选传入需求文档 |
| `devteam add` | "devteam add", "add feature", "加功能", "新增" | 给已有项目加功能 |
| `devteam debug` | "devteam debug", "debug", "修bug", "报错", "定位" | 定位修复 bug |
| `devteam deploy` | "devteam deploy", "deploy", "部署", "打镜像" | 打镜像部署服务 |
| `devteam sync` | "devteam sync", "同步skills" | 手动同步 skills → huron_skills repo |

## DevTeam Agent 名单 (11人)

| Agent | 职责 |
|-------|------|
| PM | 需求澄清，规格说明书。**支持读取解析外部需求文档** |
| Architect | 系统设计，Mermaid 架构图，技术选型 |
| Backend | FastAPI/Python API 开发 |
| Frontend | React 18+ / Vue 3 前端开发 |
| Tester | pytest + Playwright E2E，覆盖率分析 |
| Reviewer | 代码审查 + OWASP 安全检查 |
| Logging | 结构化日志 + Prometheus 指标 + 健康检查 |
| Debugger | 5步根因分析（复现→隔离→假设→修复→预防） |
| DevOps | Dockerfile + docker-compose + CI/CD 配置 |
| Deploy | docker build → push → deploy → verify |

---

## devteam build [需求文件|文件夹] — 从零搭建项目

触发: 用户说 "devteam build <描述>"  ["使用"|"参考"|"根据" <需求路径>]

### Phase 0: 开工
1. 解析用户输入，提取：
   - 项目描述（"一个博客系统"）
   - 目标目录（"放在 ~/projects/blog"）
   - **需求文件/文件夹路径**（可选："使用 /path/to/requirements.md"）
2. 如果用户没指定目录，问用户
3. `mkdir -p <path> && git init && mkdir -p specs backend frontend`

### Phase 0.5: 读取需求源 ⭐ 新增
**仅当用户提供了需求文件或文件夹时执行。**

1. **单文件** → read_file 读取全文
2. **文件夹** → search_files 列出所有文件，逐个 read_file
3. 支持的格式：.md, .txt, .yaml, .json, .toml, .yml
4. 将原始需求复制到 `specs/requirements-source/` 留存
5. 提炼关键需求要点，作为 PM 输入

### Phase 1: PM
Load `dev-team-pm` → delegate_task，context 必须包含：
- 用户原始描述
- **需求文件内容摘要**（如果 Phase 0.5 有产出）
- 目标目录
PM 产出 `specs/feature.spec.md`（EARS 格式需求规格书）

### Phase 2: Architect
Load `dev-team-architect` → delegate_task
产出 `specs/architecture.md`

### Phase 3: Plan
Load `writing-plans` → 拆解 bite-sized 任务清单

### Phase 4: 实现
dispatch Backend + Frontend Agent（不同文件可并行）

### Phase 5: Test
Load `dev-team-tester` → delegate_task

### Phase 6: Review
Load `dev-team-reviewer` → delegate_task
Critical issues → 回 Phase 4 修复 → 重新 Review

### Phase 7: Logging
Load `dev-team-logging` → delegate_task

### Phase 8: DevOps
Load `dev-team-devops` → delegate_task

### Phase 9: 验证
pytest -v + curl /api/health + git commit

### Phase 10: 同步到 huron_skills ⭐ 新增
**每次 build/add/debug/deploy 完成后自动执行：**
1. 如果执行过程中修改了任何 skill（踩坑、优化流程），记录变更
2. `cp -r ~/.hermes/skills/dev-team/* /Users/huron/code/ai_lab/huron_skills/skills/hermes/dev-team/`
3. 检查 README.md，如有新功能/流程变更则更新
4. `cd /Users/huron/code/ai_lab/huron_skills && git add skills/hermes/dev-team/ && git commit -m "devteam: sync after [build|add|debug|deploy] — <简要说明>" && git push`

---

## devteam add — 增量加功能

触发: "devteam add <功能>" 或 "给我加个 <功能>"

1. 确认项目路径 + 要加的功能
2. Load `dev-team-pm` → 澄清增量需求
3. Load `writing-plans` → 拆解增量任务
4. dispatch Backend/Frontend 逐个实现
5. Test → Review → git commit
6. **自动执行 sync**

---

## devteam debug — 定位修bug

触发: "devteam debug <bug>" 或 "帮我看看这个报错"

1. 确认项目路径 + bug 描述/报错
2. Load `dev-team-debugger` → dispatch:
   Reproduce → Isolate → Hypothesize → Fix → Prevent
3. Test → Review → git commit
4. **自动执行 sync**

---

## devteam deploy — 打镜像部署

触发: "devteam deploy" 或 "部署" 或 "打镜像"

1. 确认项目路径
2. Load `dev-team-deploy` → dispatch:
   Build → Test locally → Push → Deploy → Verify
3. **自动执行 sync**

---

## devteam sync — 手动同步到 huron_skills

触发: "devteam sync" 或 "同步skills"

1. `cp -r ~/.hermes/skills/dev-team/* /Users/huron/code/ai_lab/huron_skills/skills/hermes/dev-team/`
2. 检查 `/Users/huron/code/ai_lab/huron_skills/skills/hermes/dev-team/README.md` 是否需要更新
3. `cd /Users/huron/code/ai_lab/huron_skills && git add skills/hermes/dev-team/ && git commit -m "devteam: sync skills [timestamp]" && git push`
4. 报告同步状态：修改了哪些 skill，push 结果

---

## 需求文件格式

### 单文件模式
```
devteam build 一个博客系统 使用 ~/requirements/blog.md --dir ~/projects/blog
```

### 文件夹模式
```
devteam build ~/requirements/blog/ --dir ~/projects/blog
```
文件夹内多个 .md/.txt/.yaml 文件，PM 逐个读取分析。

### 需求文件模板（推荐格式）
```markdown
# 项目名称
## 背景
为什么做这个项目
## 功能需求
### F1: 用户系统
- 注册（email + 密码）
- 登录（JWT）
### F2: 核心功能
- 创建/编辑/删除文章
- 文章列表 + 分页
## 非功能需求
- 响应 < 200ms，并发 1000
## 技术约束
- 必须 PostgreSQL，K8s 部署
## UI 要求
- 苹果设计风格，移动端响应式
```

PM 将基于此生成正式 EARS 格式规格书。

---

## 调度规范

每次 `delegate_task` 必须包含：
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
- **build/add/debug/deploy 完成后必须自动 sync → huron_skills + push**
- 如果用户提供了需求文件，Phase 0.5 必须先读取
- 同步完成后确认 git push 成功，报告 commit hash
