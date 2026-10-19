# Harness Evolution

English | [中文](README.md)

A trace-viewing and problem-diagnosis service for coding agents (Codex first): import real execution traces, inspect goals, tool calls, errors and results turn by turn, link every problem back to evidence, and turn it into evaluable harness improvements.

## Current state

M0 engineering baseline: the pnpm workspace, React + Vite web app, Fastify + TypeScript server, shared contracts package and health check are wired together. Trace parsing, SQLite storage and diagnosis arrive milestone by milestone; boundaries live in [docs/architecture.en.md](docs/architecture.en.md).

## Quick start

```sh
pnpm install
pnpm dev
```

- Web: http://localhost:5173
- API: http://127.0.0.1:4310/api/health

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
apps/web/          React + Vite 前端
apps/server/       Fastify + TypeScript 后端
packages/contracts 前后端共享协议
docs/              工程文档（分层见 docs/AGENTS.md）
.agents/flow/      roadmap / milestone / issue 流程树
.agents/notes/     设计决策记录
.agents/skills/    PR 检视、Computer Use 等可复用技能
research/          评测任务、harness 适配与实验记录
scripts/           零依赖门禁脚本
```
