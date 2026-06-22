# DevTeam 使用说明

一句话驱动 11 人全栈开发团队。基于 Hermes Agent 的 `delegate_task` 多 Agent 调度。

## 快速开始

在 Hermes 里直接说：

```
devteam build 一个博客系统，放在 ~/projects/blog
devteam build ~/requirements/blog.md --dir ~/projects/blog   # 带需求文档
devteam build ~/requirements/ --dir ~/projects/blog          # 需求文件夹
devteam add  给博客加个评论功能
devteam debug 登录接口返回 500，帮我看看
devteam deploy 打镜像部署到服务器
devteam sync  同步 skills 到仓库
```

## 五大命令

| 命令 | 触发词 | 用途 |
|------|--------|------|
| `devteam build [需求文件\|文件夹]` | "devteam build", "build me", "创建", "搭建" | 从零搭建，**可选传入需求文档** |
| `devteam add` | "devteam add", "加功能", "新增" | 给已有项目增量加功能 |
| `devteam debug` | "devteam debug", "修bug", "报错", "定位" | 定位并修复 bug |
| `devteam deploy` | "devteam deploy", "部署", "打镜像" | 打 Docker 镜像并部署 |
| `devteam sync` | "devteam sync", "同步skills" | 手动同步 skills → huron_skills repo |

### 新特性（v2.1）

**需求文件输入**
`devteam build` 现在支持传入需求文件或文件夹。Orchestrator 会：
1. 读取并分析需求文档（.md/.txt/.yaml/.json/.toml）
2. 保存副本到 `specs/requirements-source/`
3. 交由 PM Agent 生成正式 EARS 格式规格书

**自动同步**
每次 build/add/debug/deploy 完成后，自动：
1. 同步更新的 skills 到 huron_skills 仓库
2. 更新 README（如有新增功能/流程变更）
3. git commit + push

## DevTeam 成员 (11 Agent)

### 指挥层
| Agent | Skill | 职责 |
|-------|-------|------|
| 总指挥 | dev-team-orchestrator | 接收命令，调度全队，跟踪进度，**读取需求文档，自动同步** |
| PM | dev-team-pm | 需求澄清，EARS 格式规格书，验收标准，**支持外部需求分析** |
| 架构师 | dev-team-architect | 系统设计，Mermaid 架构图，ADR 决策记录 |

### 开发层
| Agent | Skill | 技术栈 |
|-------|-------|--------|
| 后端开发 | dev-team-backend | FastAPI + Pydantic V2 + async SQLAlchemy + JWT |
| 前端开发 | dev-team-frontend | React 18+ / Vue 3 + TypeScript + Tailwind CSS |

### 质量层
| Agent | Skill | 职责 |
|-------|-------|------|
| 测试工程师 | dev-team-tester | pytest + Playwright E2E，覆盖率分析 |
| 代码审查 | dev-team-reviewer | 代码质量 + OWASP 安全检查 |
| 问题定位 | dev-team-debugger | 5 步根因分析法（复现→隔离→假设→修复→预防） |

### 运维层
| Agent | Skill | 职责 |
|-------|-------|------|
| 日志监控 | dev-team-logging | 结构化日志 + Prometheus 指标 + 健康检查 |
| DevOps | dev-team-devops | Dockerfile + docker-compose + CI/CD 配置 |
| 部署 | dev-team-deploy | docker build → push → deploy → verify |

## devteam build 完整流程 (11 Phase) ⭐ 更新

```
Phase 0  开工      → mkdir + git init
Phase 0.5 需求源   → 读取外部需求文件/文件夹（v2.1 新增）
Phase 1  PM        → 澄清需求，写 specs/feature.spec.md
Phase 2  Architect → 系统设计，specs/architecture.md
Phase 3  Plan      → 拆解 bite-sized 任务
Phase 4  实现      → Backend + Frontend Agent 并行编码
Phase 5  Test      → 写测试 + 跑测试
Phase 6  Review    → 代码审查 + 安全检查
Phase 7  Logging   → 结构化日志 + 监控 + 健康检查
Phase 8  DevOps    → Dockerfile + CI/CD
Phase 9  验证      → pytest + curl /health + git commit
Phase 10 同步      → sync skills → huron_skills + push（v2.1 新增）
```

## 技术栈默认值

- Backend: FastAPI + Pydantic V2 + async SQLAlchemy + SQLite/PostgreSQL
- Frontend: React 18 + TypeScript + Tailwind CSS + Zustand
- Auth: JWT + bcrypt
- Dev: Vite (前端) + uvicorn (后端)
- Deploy: Docker multi-stage build

## 需求文件格式

### 模板
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
## 非功能需求
- 响应 < 200ms，并发 1000
## 技术约束
- PostgreSQL，K8s 部署
## UI 要求
- 苹果设计风格，移动端响应式
```

### 使用方式
```bash
# 单文件
devteam build ~/requirements/blog-v1.md --dir ~/projects/blog

# 文件夹（多个 .md 文件）
devteam build ~/requirements/blog/ --dir ~/projects/blog

# 一行搞定（文件路径可嵌入描述中）
devteam build 一个博客系统，使用 ~/prds/blog.md，放在 ~/projects/blog
```

PM Agent 会读取需求文档，生成正式的 EARS 格式规格书。

## 调度原理

每个 Agent 通过 Hermes 的 `delegate_task` 调用，独立上下文，专用工具集。总指挥负责：

1. 加载 Agent skill 获取完整指令
2. 打包项目上下文（路径、技术栈、架构、需求文件）
3. 派发 `delegate_task` 给子 Agent
4. 验证输出 → 标记完成 → 进入下一步
5. **完成后自动 sync skills 到 git 仓库**

## 安装位置

```
~/.hermes/skills/dev-team/
├── dev-team-orchestrator/  # 总指挥 (v2.1)
├── dev-team-pm/
├── dev-team-architect/
├── dev-team-backend/
├── dev-team-frontend/
├── dev-team-tester/
├── dev-team-reviewer/
├── dev-team-debugger/
├── dev-team-logging/
├── dev-team-devops/
└── dev-team-deploy/
```

源码仓库: `github.com/lxlhero/huron_skills`，路径 `skills/hermes/dev-team/`

## 自定义

每个 Agent skill 可以独立修改。改后端技术栈？编辑 `dev-team-backend/SKILL.md`。加新 Agent？创建新 skill 并在 orchestrator 里注册。

Agent 专业知识来源于 `/Users/huron/code/ai_lab/claude-skills/skills/` 下的 65+ 个专业 skill（fastapi-expert, react-expert, test-master, code-reviewer 等）。

## 变更记录

- v2.1: 新增需求文件/文件夹输入，新增 `devteam sync` 命令，新增 Phase 0.5 和 Phase 10 自动同步
- v2.0: 新增 deploy Agent，orchestrator 支持 build/debug/add/deploy 四个命令
- v1.0: 初始版本，10 Agent，build 流程 9 Phase
