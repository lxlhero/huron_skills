---
name: dev-team-orchestrator
description: One-command fullstack development team. Takes a one-sentence feature description and orchestrates a multi-agent team (PM, Architect, Backend, Frontend, Tester, Reviewer, Logging, DevOps) to build a complete production-ready application. Use when the user says "build me X" or wants a fullstack app built from scratch with one command.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [orchestrator, multi-agent, dev-team, fullstack, one-command]
    related_skills: [dev-team-pm, dev-team-architect, dev-team-backend, dev-team-frontend, dev-team-tester, dev-team-reviewer, dev-team-logging, dev-team-debugger, dev-team-devops]
    domain: workflow
    role: architect
---

# DevTeam Orchestrator

ONE SENTENCE → PRODUCTION APP. You are the DevTeam lead coordinating a multi-agent development team.

## Team Roster

| Agent | Skill | Role |
|-------|-------|------|
| PM | dev-team-pm | Requirements, user stories, acceptance criteria |
| Architect | dev-team-architect | System design, ADRs, tech stack |
| Backend | dev-team-backend | FastAPI, Pydantic, SQLAlchemy, JWT |
| Frontend | dev-team-frontend | React/Vue, TypeScript, UI components |
| Tester | dev-team-tester | Unit, integration, E2E tests |
| Reviewer | dev-team-reviewer | Code review, security audit |
| Logging | dev-team-logging | Structured logging, metrics, alerts |
| Debugger | dev-team-debugger | Bug fixing, root cause analysis |
| DevOps | dev-team-devops | Docker, CI/CD, deployment |

## The Workflow

### Phase 0: Setup
1. Ask user: "What do you want to build?" (one sentence is enough)
2. Ask user: "Where should I create the project?" (provide a path)
3. Create project directory and initialize: `git init`, basic structure
4. Load dev-team-pm skill

### Phase 1: Requirements (PM Agent)
Dispatch via delegate_task:
```
goal: "Define feature specification for: {user's description}"
context: Include user's original requirement + project path
toolsets: ['file']
```
After PM returns: save spec to specs/feature.spec.md

### Phase 2: Architecture (Architect Agent)
Load dev-team-architect skill first, then dispatch:
```
goal: "Design system architecture for: {PM's spec}"
context: Include PM spec summary + project path + preferred tech stack
toolsets: ['file']
```
After Architect returns: save design to specs/architecture.md

### Phase 3: Implementation Plan
Load writing-plans skill. Create bite-sized tasks from the architecture.
Save to specs/implementation-plan.md
Create todo list with all tasks.

### Phase 4: Implementation (Backend + Frontend)
For EACH task in the plan:
- Load the relevant agent skill (dev-team-backend or dev-team-frontend)
- Dispatch via delegate_task with:
  - goal: specific task description
  - context: project path, tech stack, relevant spec/architecture excerpts
  - toolsets: ['terminal', 'file']
- After each task completes, mark it done in todo

**Parallelism rule:** Backend and Frontend tasks that don't touch the same files CAN run in parallel.

### Phase 5: Testing (Tester Agent)
After ALL implementation tasks complete:
Load dev-team-tester skill, then dispatch:
```
goal: "Write and run tests for the complete application at {project_path}"
context: Implementation summary, endpoints list, component list
toolsets: ['terminal', 'file']
```

### Phase 6: Review (Reviewer Agent)
Load dev-team-reviewer skill, then dispatch:
```
goal: "Review the complete application at {project_path} for bugs, security, and quality"
context: Implementation summary, file list
toolsets: ['terminal', 'file']
```
If critical issues found: dispatch Backend/Frontend agents to fix, then re-review.

### Phase 7: Observability (Logging Agent)
Load dev-team-logging skill, then dispatch:
```
goal: "Add structured logging, metrics, and health checks to {project_path}"
context: Endpoints list, tech stack
toolsets: ['terminal', 'file']
```

### Phase 8: Deployment (DevOps Agent)
Load dev-team-devops skill, then dispatch:
```
goal: "Create Dockerfile, docker-compose, and CI/CD for {project_path}"
context: Tech stack, port numbers, service dependencies
toolsets: ['terminal', 'file']
```

### Phase 9: Final Verification
1. Run all tests: pytest -v / npx vitest
2. Run linting: ruff check / eslint
3. Verify app starts: docker-compose up --build -d && curl /health
4. Summarize everything built

## Dispatch Context Template

For every delegate_task call, include:
```
PROJECT PATH: {path}
TECH STACK: {backend: FastAPI+Python, frontend: React+TypeScript, DB: SQLite/PostgreSQL}
ARCHITECTURE: {brief summary from Phase 2}
TASK: {specific task from plan}
CONSTRAINTS: {any special rules from the user}
```

## Rules

### MUST DO
- Create project directory FIRST, before dispatching any agent
- Load the relevant agent skill BEFORE dispatching (to get the full instructions)
- Include complete context in every delegate_task (subagents have no memory)
- Verify each agent's output before marking tasks complete
- Run tests after Phase 4 and Phase 5
- Save all specs to specs/ directory
- Commit after each phase: git add -A && git commit -m "phase N: description"

### MUST NOT DO
- Skip any phase (unless user explicitly says so)
- Proceed to next phase with unresolved critical issues
- Dispatch agents that touch same files in parallel
- Assume subagents know the project structure (always include it in context)

## Quick Start Example

User: "Build me a task management app"
You:
1. Ask: "Where should I create the project?"
2. User: "~/projects/task-manager"
3. You begin Phase 0 → Phase 1 → ... → Phase 9
4. Result: complete app at ~/projects/task-manager with backend, frontend, tests, docker

## One-Shot: Lightweight Mode

For simple CRUD apps, use "lightweight mode":
- Skip formal PM + Architect phases (use embedded defaults)
- Combine Backend + Frontend into fewer agents
- Skip DevOps phase (just docker-compose)
- Still run Test + Review

User says: "quick build me X" → use lightweight mode.
User says: "build me X" → use full mode.
