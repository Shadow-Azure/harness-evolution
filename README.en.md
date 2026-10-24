# Harness Evolution

English | [中文](README.md)

A trace-viewing and problem-diagnosis service for coding agents: import real execution traces, inspect goals, tool calls, errors and results turn by turn, link every problem back to evidence, and turn it into evaluable harness improvements.

## Current state

M1 engineering foundation in progress: the pnpm workspace, React + Vite web app, Python 3.12 + FastAPI server, shared contracts package and health check are wired together. Data, identity, traces and diagnosis arrive through the [roadmap](docs/roadmap.en.md); boundaries live in [architecture](docs/architecture.en.md).

## Quick start

```sh
pnpm install
pnpm setup:api
pnpm dev
```

- Web: http://localhost:5173
- API: http://127.0.0.1:8787/api/health

## Docs and gates

- Documentation map: [docs/README.en.md](docs/README.en.md)
- Documentation standard: [docs/AGENTS.md](docs/AGENTS.md)
- Bilingual pairing contract: [docs/i18n/README.en.md](docs/i18n/README.en.md)
- Development flow: [.agents/flow/README.en.md](.agents/flow/README.en.md)
- Decision records: [.agents/notes/README.en.md](.agents/notes/README.en.md)
- PR review: [docs/review.en.md](docs/review.en.md)

```sh
pnpm lint:docs     # 快速文档门禁
pnpm verify:docs   # 全量文档门禁
pnpm verify:flow   # 开发流程状态机
```

## Layout

```text
apps/web/          React + Vite frontend
apps/api/          Python 3.12 + FastAPI backend
packages/contracts Shared protocols
docs/              Engineering docs (layers in docs/AGENTS.md)
.agents/flow/      Roadmap / milestone / issue tree
.agents/notes/     Decision records
.agents/skills/    Reusable review and Computer Use skills
research/          Evaluation tasks, adapters and experiments
scripts/           Dependency-free gates
```
