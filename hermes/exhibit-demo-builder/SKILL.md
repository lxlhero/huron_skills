---
name: exhibit-demo-builder
description: Build showcaseable demo platforms from enterprise project documentation (Chinese clients).
version: 1.1.0
metadata:
  hermes:
    tags: [exhibit, demo, chinese, docker, fastapi, react]
---

# Exhibit Demo Platform Builder

Build interactive demo platforms from enterprise project documentation for Chinese-speaking clients.

## When to Use

- Given a folder of project documents (技术规范书, 需求说明书, 解决方案, 测试报告, etc.)
- Need to produce a showcaseable, clickable demo platform
- Client is Chinese-speaking, non-technical
- Delivery: single Docker image + one Chinese deployment doc

## Naming Convention (CRITICAL)

- **Directory name MUST match the original Chinese project name** from the source documents directory.
  - Correct: `一体化可视编排与集成开发工具`
  - Wrong: `visual-orchestration-ide`, `AI开发平台-Demo`
- All client-facing filenames in Chinese (e.g., `AI开发平台-镜像.tar.gz`, `部署说明.md`)
- Internal docs (需求分析, 技术方案, 交付方案) go in `docs/internal/`, never delivered to client

## Standard Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18+ / Vite / TypeScript / Ant Design 5 / React Router 6 |
| Visual Builder | @xyflow/react (React Flow v12) for node-based orchestration |
| Backend | Python FastAPI + SQLAlchemy + SQLite |
| Container | Single Docker image via supervisord (nginx + uvicorn) |

## UI Theme (CRITICAL)

**Enterprise blue-white, light theme — NOT dark theme.**
```
ConfigProvider theme={{ token: { colorPrimary: '#1677ff' } }}
```
- White backgrounds, blue (#1677ff) as primary accent
- Ant Design default light theme (no darkAlgorithm)
- Clean, professional, enterprise-grade look
- Sidebar: #fafafa or white; Header: white with subtle border-bottom
- User explicitly rejected dark theme — never use it

## Architecture

```
<项目中文名>/
├── docs/
│   ├── 部署说明.md            ← ONLY client-facing doc
│   └── internal/              ← NOT delivered to client
│       ├── 需求分析.md
│       ├── 技术方案.md
│       ├── 交付方案.md
│       └── <项目名>-镜像.tar.gz
├── Dockerfile.single          ← Single-image build
├── supervisord.conf           ← nginx + uvicorn process manager
├── nginx-single.conf          ← Serves static + proxies /api/ → 127.0.0.1:8000
├── start.sh                   ← Entrypoint wrapper
├── backend/                   ← FastAPI app
│   ├── main.py                ← REST API endpoints
│   ├── database.py            ← SQLAlchemy models + seed data
│   ├── Dockerfile
│   └── requirements.txt
├── src/                       ← React frontend
│   ├── services/api.ts        ← API service layer (fetch wrapper)
│   ├── pages/                 ← Page components
│   ├── components/            ← Reusable components
│   ├── mock/data.ts           ← Keep for reference, but pages use api.ts
│   └── theme.ts               ← Ant Design light enterprise blue-white theme
├── docker-compose.yml         ← Dev mode (two containers, NOT for client delivery)
└── Dockerfile                 ← Frontend-only build (legacy, kept for dev)
```

## Workflow

### Phase 1: Analysis
1. Extract key documents from the project folder using python-docx:
   - 技术规范书 (overview, requirements scope)
   - 用户需求说明书 (detailed requirements)
   - 整体解决方案 (architecture, tech stack)
   - 系统界面截图及说明 (UI reference)
2. Write 需求分析.md to docs/internal/ summarizing: project overview, core modules, tech stack, demo scope

### Phase 2: Plan (delegate to Claude Code / subagent)

Evaluate the technical approach using the **5-dimension weighted scoring framework** (full details in [references/tech-eval-framework.md](references/tech-eval-framework.md)). Quick reference:

| Dimension | Weight | What to check |
|-----------|--------|---------------|
| Feature match | 30% | How much of the requirement does the OSS project cover? |
| Customization cost | 25% | How hard is it to modify/extend? |
| Stack compatibility | 20% | Does it fit our FastAPI+React+Docker stack? |
| Maintenance risk | 15% | Is the project actively maintained? Community size? |
| Demo suitability | 10% | Can it run with just SQLite, no external deps? |

Score each 1-5, weighted sum ≥ 3.5 → use open-source; < 3.5 → build from scratch.

Common OSS candidates and their typical scores:
- **Dify** (LLM app builder) → ~3.8 — best for Agent/knowledge-base/chatbot projects
- **RAGFlow** (RAG knowledge base) → ~3.5 — document parsing + QA
- **LangFlow** (LangChain visual) → ~3.7 — visual LLM orchestration
- **n8n** (workflow automation) → ~3.2 — powerful but frontend stack mismatch (Vue)
- **FastGPT** (knowledge QA) → ~3.4 — good but heavy for simple demos

For projects 2-10 pre-judgments, see the framework doc.

After deciding the approach, define demo scope (4-6 pages: login, dashboard, list/table, core feature page) and write 技术方案.md to docs/internal/.

### Phase 3: Implement (delegate_task with terminal+file+web toolsets)
1. Backend first: FastAPI + SQLite + seed data matching mock structures exactly
2. Frontend: React + Vite + Ant Design light enterprise blue-white theme + React Router
3. API service layer replacing hardcoded mock data
4. Single-image Docker packaging: supervisord + nginx + uvicorn

### Phase 4: Delivery
1. Write 部署说明.md (Chinese, for non-technical users):
   - Prerequisites: Install Docker Desktop (with download links)
   - Step 1: docker load -i <image>.tar.gz
   - Step 2: docker run -d -p 3000:80 --name <name> <image>
   - Step 3: Open http://localhost:3000
   - **CRITICAL: 演示账号表** — 列出所有预置用户的用户名、密码、角色、权限。让客户拿到就能登。格式：
     ```
     ## 演示账号
     | 用户名 | 密码 | 角色 | 权限说明 |
     |-------|------|------|---------|
     | **admin** | admin123 | 管理员 | 全部权限 |
     ```
     不要写"密码任意"、"不校验密码"之类的话，显得不专业。
   - Stop/start/restart commands
   - Upgrade procedure
   - Backup procedure
   - FAQ (connection issues, port conflicts, data safety)
   - Support contact info
2. Export image: `docker save <image> | gzip > <中文名>-镜像.tar.gz`
3. Write 交付方案.md to docs/internal/

## Client Deliverable (2 files only)

```
<项目名>-镜像.tar.gz     ← Docker image
部署说明.md              ← Deployment guide
```

## Key Rules

1. **Always backend + database** — pure frontend mockups are rejected. Every interactive feature must call real APIs.
2. **Chinese filenames** for everything client-facing. Original project name for directory.
3. **Internal docs stay internal** — docs/internal/ is never delivered.
4. **Single image delivery** — merge frontend+backend into one container with supervisord.
5. **Delegate complex implementation** — use delegate_task with terminal+file+web toolsets. Claude Code CLI may have auth issues with long prompts.
6. **Pre-seed database** — SQLite with all mock data on first run. Image is fully self-contained; NO volume mounts in deployment commands. Database lives inside the container.
7. **Demo accounts in 部署说明** — every project with login MUST list all seeded usernames, passwords, roles, and permissions. 不要写"密码任意"、"不校验密码"之类的话，显得不专业。后端必须实际校验密码。
8. **Docker image tag is English** — 镜像 tag 必须用英文（如 `knowledge-base-manager:latest`）。部署文档里的 `docker run xxx:latest` 必须用英文 tag，中文项目名只是目录名和 `.tar.gz` 文件名。
9. **Login must send password** — 前端登录必须把 `password` 字段传给后端。LoginParams 接口必须包含 `password: string`。后端的 login 端点必须校验密码，不匹配返回 401。
10. **Delivery folder structure** — 每个项目一个子目录，里面只有两个文件：`部署说明.md` + `<中文名>-镜像.tar.gz`。整体交付打包为 `delivery.tar.gz`。

## Pitfalls

- Docker Compose V2 command is `docker compose` (no hyphen), V1 is `docker-compose`
- Long prompts to Claude Code CLI may get 403 from proxy; use delegate_task as fallback
- `docker-compose.yml` `version` attribute is deprecated in recent Docker, omit it
- supervisord binary location varies: check `/usr/bin/supervisord` vs `/usr/local/bin/supervisord`
- Container name conflicts: always `docker rm -f <name>` before re-creating
- **tsconfig 常见错误**：
  - `allowImportingTsExtensions` 必须搭配 `noEmit` 或 `emitDeclarationOnly`，否则 `tsc -b` 失败
  - `composite: true` + `noEmit: true` 互斥，二选一
  - 推荐方案：tsconfig.json 不设 references，直接 `include: ["src", "vite-env.d.ts"]`，build 用 `tsc --noEmit && vite build`
  - `esModuleInterop: true` 避免 import 报错
  - **演示文档禁忌**：部署说明.md 里绝对不能出现"密码任意"、"不校验密码"、"任意用户名可登录"等字样，客户看到会觉得是玩具。必须像正式系统一样列出用户名+密码。
  - **Docker tag 必须英文**：`docker build -t <英文名>:latest`，`docker run <英文名>:latest`。中文项目名只用于目录名和 tar.gz 文件名，不在 Docker 命令中。
  - **部署文档命令核实**：交付前必须 grep 所有部署文档确认 docker run 用的是英文 tag，`-v` 已删除。
