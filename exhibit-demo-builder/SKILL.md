---
name: exhibit-demo-builder
description: Build showcaseable demo platforms from enterprise project documentation (Chinese clients).
version: 1.0.0
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
│   └── theme.ts               ← Ant Design dark theme config
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
2. Frontend: React + Vite + Ant Design dark theme + React Router
3. API service layer replacing hardcoded mock data
4. Single-image Docker packaging: supervisord + nginx + uvicorn

### Phase 4: Delivery
1. Write 部署说明.md (Chinese, for non-technical users):
   - Prerequisites: Install Docker Desktop (with download links)
   - Step 1: docker load -i <image>.tar.gz
   - Step 2: docker run -d -p 3000:80 -v <volume>:/app/data --name <name> <image>
   - Step 3: Open http://localhost:3000
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
6. **Pre-seed database** — SQLite with all mock data on first run, data persists in Docker volume.

## Pitfalls

- Docker Compose V2 command is `docker compose` (no hyphen), V1 is `docker-compose`
- Long prompts to Claude Code CLI may get 403 from proxy; use delegate_task as fallback
- `docker-compose.yml` `version` attribute is deprecated in recent Docker, omit it
- supervisord binary location varies: check `/usr/bin/supervisord` vs `/usr/local/bin/supervisord`
- Container name conflicts: always `docker rm -f <name>` before re-creating
