# DevTeam 使用说明

一句话驱动 15 人全栈开发团队。基于 Hermes Agent 的 `delegate_task` 多 Agent 调度。

## 快速开始

在 Hermes 里直接说：

```
devteam build 一个博客系统，放在 ~/projects/blog
devteam build ~/requirements/blog-prd.md --dir ~/projects/blog    ← 带需求文档
devteam build ~/requirements/ --dir ~/projects/blog              ← 带需求文件夹
devteam add  给博客加个评论功能
devteam debug 登录接口返回 500，帮我看看
devteam deploy 打镜像部署到服务器
devteam expose 暴露到公网，让我手机上能访问
devteam sync  同步 skills 到 huron_skills 仓库
```

## 六大命令

| 命令 | 触发词 | 用途 |
|------|--------|------|
| `devteam build [需求文件\|文件夹]` | "devteam build", "build me", "创建", "搭建" | 从零搭建新项目，可选传入需求文档 |
| `devteam add` | "devteam add", "加功能", "新增" | 给已有项目增量加功能 |
| `devteam debug` | "devteam debug", "修bug", "报错", "定位" | 定位并修复 bug |
| `devteam deploy` | "devteam deploy", "部署", "打镜像" | 打 Docker 镜像并部署 |
| `devteam expose` | "devteam expose", "暴露", "公网访问" | 对外暴露服务（仅用户明确要求） |
| `devteam sync` | "devteam sync", "同步skills" | 同步 ~/.hermes/skills/dev-team → huron_skills 推送 |

## 新特性：需求文档驱动 + 混合输入

**v3.0** 沿袭 v2.2 四种输入模式：纯描述、纯文件、纯文件夹、**文件+描述混合**。

### 混合输入模式
```
devteam build ~/requirements/blog-prd.md 我需要ui明快漂亮一点 --dir ~/projects/blog
devteam build ~/requirements/blog-prd.md 再加评论功能和暗黑模式 --dir ~/projects/blog
devteam build ~/requirements/ 不要用户系统，只要文章CRUD --dir ~/projects/blog
```
文件提供主干结构，口头描述做增量/删除/覆盖。冲突时口头描述优先。

## DevTeam 成员 (15 Agent)

### 指挥层
| Agent | Skill | 职责 |
|-------|-------|------|
| 总指挥 | dev-team-orchestrator | 接收命令，调度全队，跟踪进度 |
| PM | dev-team-pm | 需求澄清，EARS 格式规格书，支持读取外部需求文档 |
| 架构师 | dev-team-architect | 系统设计，Mermaid 架构图，ADR 决策记录，输出高层实体关系 + 设计风格要求 |

### 数据 & 设计层（v3.0 新增）
| Agent | Skill | 职责 |
|-------|-------|------|
| 数据库 | dev-team-database | 基于架构师实体关系设计完整 ER 图 → 建表 SQL → Alembic 迁移脚本 → 种子数据。后端不允许直接改表 |
| UI 规范 | dev-team-ui | 遵循架构师设计风格生成 Design Tokens（JSON+CSS）→ 基础组件样式规范。前端只能引用 token，禁止硬编码样式值 |

### 开发层
| Agent | Skill | 技术栈 |
|-------|-------|--------|
| 后端开发 | dev-team-backend | FastAPI + Pydantic V2 + async SQLAlchemy + JWT |
| 前端开发 | dev-team-frontend | React 18+ / Vue 3 + TypeScript + Tailwind CSS |

### 质量层（v3.0 拆分测试 Agent）
| Agent | Skill | 职责 |
|-------|-------|------|
| 测试编写 | dev-team-test-writer | 读取代码 → 梳理场景 → 编写 pytest/Vitest/Playwright 测试 |
| 测试执行 | dev-team-test-runner | 运行测试 → 分类错误（业务bug/脚本错误/环境问题）→ 通知对应 agent → 覆盖率报告 |
| 代码审查 | dev-team-reviewer | 代码质量 + OWASP 安全检查 |
| 问题定位 | dev-team-debugger | 5 步根因分析法（复现→隔离→假设→修复→预防） |

### 观测 & 运维层
| Agent | Skill | 职责 |
|-------|-------|------|
| 结构化日志 | dev-team-logging | 结构化日志 + Prometheus 指标 + 健康检查 |
| 变更追踪 | dev-team-log-tracker | 自主扫描变更 → 维护台账 → 响应查询，只读不写（v3.0 新增） |
| DevOps | dev-team-devops | Dockerfile + docker-compose + CI/CD 配置 |
| 部署 | dev-team-deploy | docker build → push → deploy → verify |
| 对外暴露 | dev-team-deploy-expose | Tailscale Funnel / Cloudflare Tunnel 公网暴露（v3.0 新增，仅用户明确要求时激活） |

## devteam build 完整流程 (12 Phase)

```
Phase 0   开工           → mkdir + git init
Phase 0.5 读取需求       → 如果提供了需求文件/文件夹，读取分析
Phase 1   PM             → 澄清需求，写 specs/feature.spec.md
Phase 2   Architect      → 系统设计，specs/architecture.md（含实体关系 + 设计风格）
Phase 2.5 Database(v3.0) → ER 图 → 建表 SQL → 迁移 → 种子数据
Phase 2.6 UI(v3.0)       → Design Tokens → CSS 变量 → 组件样式规范
Phase 3   Plan           → 拆解 bite-sized 任务
Phase 4   实现           → Backend + Frontend Agent 并行编码
Phase 5a  Test-Write     → 编写测试代码（pytest/Vitest/Playwright）
Phase 5b  Test-Run       → 执行测试 → 分类错误 → 覆盖率报告
Phase 6   Review         → 代码审查 + 安全检查
Phase 7   Logging        → 结构化日志 + 监控 + 健康检查
Phase 8   DevOps         → Dockerfile + CI/CD
Phase 9   验证           → pytest + curl /health + git commit
Phase 10  Log-Track(v3.0)→ 初始化变更台账
Phase 11  同步           → devteam sync（自动推送到 huron_skills）
```

## 关键设计原则

1. **Database Agent 是表结构唯一入口** — 后端不允许直接修改数据表，变更必须通过 orchestrator 提交数据库 agent
2. **前端只能引用 Design Tokens** — 禁止硬编码颜色、字体、间距等样式值
3. **测试写跑分离** — Test-Writer 不运行测试，Test-Runner 不写代码
4. **Log-Tracker 只读不写** — 自主扫描采集变更，不修改任何文件
5. **Deploy-Expose 按需激活** — build/add/debug 流程不自动暴露公网

## 技术栈默认值

- Backend: FastAPI + Pydantic V2 + async SQLAlchemy + SQLite/PostgreSQL
- Frontend: React 18 + TypeScript + Tailwind CSS + Zustand
- DB: SQLite (dev) / PostgreSQL (prod)，Alembic 迁移
- Auth: JWT + bcrypt
- Design: Apple 风格（无明确要求时），Design Tokens 体系
- Dev: Vite (前端) + uvicorn (后端)
- Deploy: Docker multi-stage build

## 调度原理

每个 Agent 通过 Hermes 的 `delegate_task` 调用，独立上下文，专用工具集。总指挥负责：

1. 加载 Agent skill 获取完整指令
2. 打包项目上下文（路径、技术栈、架构、关键文件路径）
3. 派发 `delegate_task` 给子 Agent
4. 验证输出 → 标记完成 → 进入下一步

## 安装位置

```
~/.hermes/skills/dev-team/
├── dev-team-orchestrator/
├── dev-team-pm/
├── dev-team-architect/
├── dev-team-database/       ← v3.0 新增
├── dev-team-ui/             ← v3.0 新增
├── dev-team-backend/
├── dev-team-frontend/
├── dev-team-tester/         ← 已标记 deprecated，保留兼容
├── dev-team-test-writer/    ← v3.0 新增（从 tester 拆分）
├── dev-team-test-runner/    ← v3.0 新增（从 tester 拆分）
├── dev-team-reviewer/
├── dev-team-debugger/
├── dev-team-logging/
├── dev-team-log-tracker/    ← v3.0 新增
├── dev-team-devops/
├── dev-team-deploy/
└── dev-team-deploy-expose/  ← v3.0 新增
```

源码仓库: `github.com/lxlhero/huron_skills`，路径 `skills/hermes/dev-team/`

## 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v3.0 | 2026-06-22 | 拆分 tester→test-writer+test-runner；新增 database、ui、log-tracker、deploy-expose 四个 agent；Pipeline 从 11 步扩展为 12 步 |
| v2.2 | 2026-06-22 | 新增混合输入模式（文件+描述并存），需求文件为主、口头描述增量/覆盖 |
| v2.1 | 2026-06-22 | 新增需求文件/文件夹输入支持、devteam sync 命令、Phase 10 自动同步 |
| v2.0 | 2026-06-22 | 新增 deploy agent，orchestrator 支持 build/debug/add/deploy 四个命令 |
| v1.0 | 2026-06-22 | 初始版本，10 agent + orchestrator |
