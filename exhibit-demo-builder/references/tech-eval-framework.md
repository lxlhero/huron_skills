# Technical Evaluation Framework: Open-Source vs Self-Build

Use this 5-dimension weighted scoring framework to decide whether to adapt an open-source
project or build from scratch for each demo platform.

## Scoring Formula

```
total = (feature_match × 0.30) + (customization_cost × 0.25) + (stack_compat × 0.20)
      + (maintenance_risk × 0.15) + (demo_suitability × 0.10)
```

- **≥ 3.5** → Use open-source secondary development
- **< 3.5** → Build from scratch

Document the score and reasoning in 技术方案.md.

---

## Dimension 1: Feature Match (Weight: 30%)

How well does the OSS project's core functionality cover the requirements?

| Score | Meaning |
|-------|---------|
| 5 | Covers 90%+ of requirements; gaps fillable via config/plugins |
| 4 | Covers 70-90%; minor custom dev needed |
| 3 | Covers 50-70%; moderate dev effort |
| 2 | Covers 30-50%; significant rewrite |
| 1 | Covers <30%; nearly total rebuild |

## Dimension 2: Customization Cost (Weight: 25%)

How difficult is it to modify and extend the OSS project?

| Score | Meaning |
|-------|---------|
| 5 | Clean architecture, excellent docs, trivial to extend |
| 4 | Reasonable structure, need source reading, scope is controlled |
| 3 | Deep internal understanding needed, changes touch multiple modules |
| 2 | Tightly coupled, modifications likely introduce bugs |
| 1 | Nearly impossible to customize, better to rewrite |

## Dimension 3: Stack Compatibility (Weight: 20%)

Does the tech stack fit our standard (Python/FastAPI backend + React frontend + Docker)?

| Score | Meaning |
|-------|---------|
| 5 | Fully compatible (Python+React), lightweight |
| 4 | Backend compatible, frontend needs adaptation |
| 3 | Needs bridge layer or multi-language mixed deployment |
| 2 | Completely different stack, extra infrastructure needed |
| 1 | Special runtime required, demo-ification extremely difficult |

## Dimension 4: Maintenance Risk (Weight: 15%)

Is the project actively maintained? Will it be around in a year?

| Score | Meaning |
|-------|---------|
| 5 | Very active, corporate backing, mature community |
| 4 | Active maintenance, stable community |
| 3 | Moderate update frequency, critical bugs get fixed |
| 2 | Slow updates, issue backlog growing |
| 1 | Nearly stalled, risk of abandonment |

## Dimension 5: Demo Suitability (Weight: 10%)

Can it be trimmed to a standalone demo (no external Redis/ES/PG dep)?

| Score | Meaning |
|-------|---------|
| 5 | Naturally demo-friendly, SQLite-only, modern UI |
| 4 | Minor tweaks needed (remove external deps), generally suitable |
| 3 | Moderate trimming needed, core features can be demoed |
| 2 | Heavy refactoring needed for demo |
| 1 | Nearly impossible to demo, too heavyweight |

---

## Worked Example

Evaluating **Dify** for a knowledge-base chatbot project:

```
Feature match:     4 × 0.30 = 1.20   (covers 80%, missing custom pipeline)
Customization:     3 × 0.25 = 0.75   (deep internal coupling, multi-module changes)
Stack compat:      4 × 0.20 = 0.80   (Python+React, needs Docker compose → single image)
Maintenance:       4 × 0.15 = 0.60   (active, corporate-backed)
Demo suitability:  3 × 0.10 = 0.30   (needs Redis removal, SQLite migration)
                                ─────
Total: 3.65 → Use Dify (recommended)
```

---

## OSS Candidate Catalog

| Project | Best For | Stack | Typical Score |
|---------|----------|-------|---------------|
| **Dify** | LLM app builder, Agents, Knowledge bases | Python+React | 3.8 |
| **RAGFlow** | RAG knowledge base, document parsing | Python+React | 3.5 |
| **LangFlow** | LangChain visual orchestration | Python+React | 3.7 |
| **n8n** | Workflow automation | TypeScript+Vue | 3.2 (frontend mismatch) |
| **FastGPT** | Knowledge QA, chatbots | TypeScript+React | 3.4 |
| **Flowise** | LLM flow orchestration | TypeScript+React | 3.5 |
| **Activepieces** | Automation workflows | TypeScript+Angular | 2.8 |
| **Build from scratch** | Highly custom scenarios | FastAPI+React | 3.0 (baseline) |

---

## 10-Project Pre-Judgments (pre-analysis, to be confirmed)

| # | Project | Prediction | Rationale |
|---|---------|-----------|-----------|
| 1 | 一体化可视编排工具 | n8n-adapt or self-build | n8n matches partially, Vue frontend incompatible |
| 2 | 领域知识库管理 | RAGFlow/Dify | Core capability match |
| 3 | 智能体组装测试 | Dify | Agent orchestration is Dify's strength |
| 4 | 智能数据问答 | FastGPT/Dify | Standard RAG scenario |
| 5 | 合成数据生成引擎 | Self-build | High domain specificity, few OSS options |
| 6 | 异构模型协同 | Self-build | Extreme customization |
| 7 | 文件加密传输中间件 | Self-build | Infrastructure middleware, no OSS match |
| 8 | 数据湖与分层存储 | Self-build | Infrastructure, demo needs heavy abstraction |
| 9 | AI家庭医生2.0 | Dify | Conversational AI app |
| 10 | AI算力服务 | Self-build | Resource management, demo needs simulation |
