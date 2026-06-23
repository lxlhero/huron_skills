---
name: dev-team-orchestrator
description: "DevTeam master controller v3.1. Seven commands: devteam build (create from scratch), devteam add (add features), devteam optimize (improve existing project — UI/logging/testing/perf), devteam debug (fix bugs), devteam deploy (build image and deploy), devteam expose (public access), devteam sync (sync skills to repo). Coordinates 15 specialized agents. Auto-syncs skills to huron_skills repo."
version: 3.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [orchestrator, multi-agent, devteam, build, debug, add, deploy, expose, requirements, sync]
    related_skills: [dev-team-pm, dev-team-architect, dev-team-database, dev-team-ui, dev-team-backend, dev-team-frontend, dev-team-test-writer, dev-team-test-runner, dev-team-reviewer, dev-team-logging, dev-team-log-tracker, dev-team-debugger, dev-team-devops, dev-team-deploy, dev-team-deploy-expose]
    domain: workflow
    role: architect
---

# DevTeam Orchestrator v3.1

DevTeam 总指挥。七个命令入口 + 需求文件/混合输入 + 自动同步。

## 命令入口

| 命令 | 触发词 | 用途 |
|------|--------|------|
| `devteam build [需求文件\|文件夹]` | "devteam build", "build me", "创建", "搭建" | 从零搭建新项目。可选传入需求文档 |
| `devteam add` | "devteam add", "add feature", "加功能", "新增" | 给已有项目加功能 |
| `devteam optimize` | "devteam optimize", "优化", "改进", "提升", "增加日志", "加测试", "优化UI" | 对已有项目做专项优化（UI/日志/测试/性能/安全） |
| `devteam debug` | "devteam debug", "debug", "修bug", "报错", "定位" | 定位修复 bug |
| `devteam deploy` | "devteam deploy", "deploy", "部署", "打镜像" | 打镜像部署服务 |
| `devteam expose` | "devteam expose", "暴露", "公网访问", "对外" | 对外暴露服务（仅用户明确要求） |
| `devteam sync` | "devteam sync", "同步skills" | 手动同步 skills 到 huron_skills |

## DevTeam Agent 名单 (15人)

### 指挥层
| Agent | 职责 |
|-------|------|
| PM | 需求澄清，EARS 格式规格说明书 |
| Architect | 系统设计，架构图，技术选型 |

### 数据 & 设计层（v3.0 新增）
| Agent | 职责 |
|-------|------|
| Database | ER 图 → 建表 SQL → 迁移脚本 → 种子数据。后端不允许直接改表 |
| UI | Design tokens → CSS 变量 → 组件样式规范。前端只能引用 token |

### 开发层
| Agent | 职责 |
|-------|------|
| Backend | FastAPI/Python API 开发 |
| Frontend | React/Vue 前端开发 |

### 质量层（v3.0 拆分）
| Agent | 职责 |
|-------|------|
| Test-Writer | 编写测试代码（pytest/Vitest/Playwright） |
| Test-Runner | 执行测试 → 分类错误 → 通知对应 agent |
| Reviewer | 代码审查 + OWASP 安全检查 |
| Debugger | 5 步根因分析（复现→隔离→假设→修复→预防） |

### 观测 & 运维层
| Agent | 职责 |
|-------|------|
| Logging | 结构化日志 + Prometheus 指标 + 健康检查 |
| Log-Tracker | 自主扫描变更 → 维护台账 → 响应查询（v3.0 新增） |
| DevOps | Dockerfile + docker-compose + CI/CD 配置 |
| Deploy | docker build → push → deploy → verify |
| Deploy-Expose | 公网暴露（Tailscale Funnel/Cloudflare Tunnel，仅用户明确要求） |

---

## devteam build — 从零搭建项目

trigger: 用户说 "devteam build <描述> [<需求文件|文件夹>] [--dir <目录>]"

支持三种输入模式:
| 模式 | 示例 | 说明 |
|------|------|------|
| 纯描述 | `devteam build 一个博客系统` | 只用自然语言描述需求 |
| 纯文件/文件夹 | `devteam build ~/prd.md --dir ~/blog` | 只用需求文档 |
| **混合输入** | `devteam build ~/prd.md 再加评论功能和暗黑模式 --dir ~/blog` | 需求文档 + 口头补充 |

### Phase 0: 开工
1. 解析用户输入，提取三要素
2. 如果用户没指定目录，问用户
3. `mkdir -p <path> && git init && mkdir -p specs backend frontend`

### Phase 0.5: 读取需求（如果有需求源）
1. 文件/文件夹 → read_file 读取
2. 合并策略：文件内容为主，口头描述为补充。冲突时口头描述优先
3. 提炼合并后的需求要点摘要，传给 Phase 1 PM

### Phase 1: PM
Load `dev-team-pm` → delegate_task
产出: `specs/feature.spec.md`（EARS 格式需求规格书）

### Phase 2: Architect
Load `dev-team-architect` → 系统设计
产出: `specs/architecture.md`（包含技术选型、高层实体关系、设计风格要求）

### Phase 2.5: Database（v3.0 新增）
Load `dev-team-database` → delegate_task
context 包含: specs/architecture.md 中的实体关系 + 技术选型（数据库类型）
产出: `specs/er-diagram.md`, `backend/migrations/`, `specs/schema.sql`, `specs/seed.sql`

### Phase 2.6: UI（v3.0 新增）
Load `dev-team-ui` → delegate_task
context 包含: specs/architecture.md 中的设计风格 + 终端类型
产出: `specs/design-tokens.json`, `specs/design-tokens.css`, `specs/ui-spec.md`

### Phase 3: Plan
Load `writing-plans` → 拆成 bite-sized 任务清单
**注意**: 前端任务需注明"引用 design tokens，禁止硬编码样式值"
**注意**: 后端任务需注明"表结构变更通过 orchestrator 提交 database agent"

### Phase 4: 实现
按任务 dispatch:
- Backend → `delegate_task` + dev-team-backend context（包含 schema.sql 路径）
- Frontend → `delegate_task` + dev-team-frontend context（包含 design-tokens.css 路径 + UI 规范）
不同文件的 Backend/Frontend 可并行

### Phase 5: Test（v3.0 拆分为二）

**Phase 5a: Test-Writer**
Load `dev-team-test-writer` → delegate_task
产出: 测试文件

**Phase 5b: Test-Runner**
Load `dev-team-test-runner` → delegate_task
产出: `specs/test-report.md`, `specs/bug-list.md`

如果 test-runner 报告测试脚本错误 → 回到 Phase 5a（test-writer 修复）
如果 test-runner 报告业务 bug → 回到 Phase 4（backend/frontend 修复）
如果 test-runner 报告环境问题 → orchestrator 调整后重跑 Phase 5b

### Phase 6: Review
Load `dev-team-reviewer` → delegate_task
Critical issues → 回 Phase 4 → 重新 Review

### Phase 7: Logging
Load `dev-team-logging` → delegate_task
产出: 结构化日志配置 + 健康检查端点

### Phase 8: DevOps
Load `dev-team-devops` → delegate_task
产出: Dockerfile + docker-compose + CI/CD

### Phase 9: 验证
`pytest -v` + `curl /api/health` + git commit

### Phase 10: Log-Tracker（v3.0 新增）
Load `dev-team-log-tracker` → delegate_task
产出: `specs/change-log.md`（初始化台账）

### Phase 11: 同步 Skill（自动）
完成构建后自动执行 `devteam sync`，将更新的 skill 同步到 huron_skills 仓库。

---

## devteam add — 增量加功能

触发: "devteam add <功能>"

1. 确认项目路径 + 要加的功能
2. Load `dev-team-pm` → 澄清增量需求
3. Load `writing-plans` → 拆解增量任务
4. dispatch Backend/Frontend 逐个实现
5. Phase 5a Test-Writer → Phase 5b Test-Runner
6. Review → git commit
7. 自动执行 `devteam sync`

---

## devteam optimize — 专项优化（v3.1 新增）

触发: "devteam optimize <优化方向>" 或 "优化UI"、"增加日志系统"、"加自动化测试"、"提升性能"

对已有项目做定向优化，根据优化方向调度对应 agent。

### 优化方向与 Agent 映射

| 用户表述 | 优化方向 | 调度 Agent | 产出 |
|---------|---------|-----------|------|
| "优化UI", "改进界面", "统一风格" | UI 优化 | UI Agent → Frontend Agent | 新版 design tokens + 组件样式 + 页面适配 |
| "增加日志", "加监控", "日志系统" | 日志增强 | Logging Agent → Backend/Frontend | 结构化日志 + 健康检查 + 指标埋点 |
| "加测试", "提高覆盖率", "自动化测试" | 测试补强 | Test-Writer → Test-Runner | 新测试文件 + 覆盖率报告 |
| "提升性能", "优化速度", "慢了" | 性能优化 | Architect(分析) → Backend/Frontend | 瓶颈分析 + 代码优化 + 前后对比 |
| "安全检查", "漏洞修复" | 安全加固 | Reviewer → Backend/Frontend | 安全报告 + 修复 commit |
| "加文档", "完善README" | 文档补全 | PM → 各 Agent 汇总 | README/API 文档/注释 |

### 工作流程

1. **确认项目路径 + 优化方向**
2. **现状审计**：根据优化方向，先让对应的 agent 审计当前状态
   - UI: UI Agent 检查现有 tokens/样式是否规范
   - 日志: Logging Agent 检查现有日志覆盖情况
   - 测试: Test-Runner 先跑一遍现有测试 → 出覆盖率报告
   - 性能: Architect 分析现有架构瓶颈
3. **制定优化计划**：基于审计结果，输出 `specs/optimize-plan.md`
4. **执行优化**：按计划调度 agent
5. **验证效果**：
   - UI: 前端编译 + 截图对比
   - 日志: 检查日志输出 + 健康检查
   - 测试: Test-Runner 重跑 → 覆盖率对比（优化前 vs 优化后）
   - 性能: 前后 benchmark 对比
6. **Review → git commit**
7. 自动执行 `devteam sync`

### 常见用法

```
devteam optimize 优化ui，统一成apple风格
devteam optimize 增加日志系统
devteam optimize 加自动化测试，覆盖率提到80%
devteam optimize 提升性能，首页加载太慢
devteam optimize 安全检查
devteam optimize 完善文档
```

### 多方向优化

如果用户同时提多个方向（如"优化UI和加测试"），按依赖顺序执行：
UI → 测试 → 日志 → 性能 → 安全

---

## devteam debug — 定位修bug

触发: "devteam debug <bug>"

1. 确认项目路径 + bug 描述/报错
2. Load `dev-team-log-tracker` → 查询相关变更（可选，辅助定位）
3. Load `dev-team-debugger` → dispatch: Reproduce → Isolate → Hypothesize → Fix → Prevent
4. Phase 5a Test-Writer → Phase 5b Test-Runner
5. Review → git commit
6. 自动执行 `devteam sync`

---

## devteam deploy — 打镜像部署

触发: "devteam deploy"

1. 确认项目路径
2. Load `dev-team-deploy` → dispatch: Build → Test locally → Push → Deploy → Verify
3. 自动执行 `devteam sync`

---

## devteam expose — 对外暴露（v3.0 新增）

触发: "devteam expose" 或 "暴露到公网"

**仅在用户明确要求时执行。build/add/debug 流程不自动触发。**

1. 确认项目路径 + 要暴露的服务
2. Load `dev-team-deploy-expose` → dispatch
3. 产出公网 URL + `specs/deploy-expose.md`
4. 自动执行 `devteam sync`

---

## devteam sync — 同步 Skill 到 huron_skills

1. `cp -r ~/.hermes/skills/dev-team/* /Users/huron/code/ai_lab/huron_skills/skills/hermes/dev-team/`
2. `cd /Users/huron/code/ai_lab/huron_skills && git add skills/hermes/dev-team/ && git commit -m "devteam: sync skills v3.0 [简要说明]" && git push`

---

## 调度规范

每次 `delegate_task` 必须包含:
```
PROJECT PATH: /absolute/path
TECH STACK: <backend + frontend + db>
TASK: <具体任务>
CONSTRAINTS: <特殊要求>
RELATED FILES: <关键文件路径列表（schema.sql, design-tokens.css 等）>
```

## 铁律
- 先建目录再派 Agent
- Load agent skill BEFORE dispatch
- delegate_task context 必须完整（子 Agent 无记忆）
- 每 phase git commit
- Critical issue 不解决不进下一 phase
- 不同文件的 Agent 可并行，同文件必须串行
- **build/add/debug/deploy 完成后自动执行 sync → huron_skills**
- Database Agent 是表结构的唯一入口，后端不允许直接改表
- 前端只能引用 design tokens，禁止硬编码样式值
- Deploy-Expose Agent 仅在用户明确要求时激活
