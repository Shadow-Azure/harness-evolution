# Architecture

English | [中文](architecture.md)

Records the current service boundaries, data flow and data-layer strategy. Implementation advances slice by slice; this page states the present, while rationale lives in `.agents/notes/`.

## Product boundary

Currently Codex only:

1. Import Codex session traces from this machine.
2. Browse messages, reasoning, tool calls, outputs and errors turn by turn in the web app.
3. Diagnose traces with rules or AI.
4. Link every finding back to concrete trace evidence and turn it into an actionable improvement.

Claude Code, automatic skill rewriting and the comparative-evaluation loop belong to later milestones, outside the M1 slice.

## Service split

| Unit | Technology | Responsibility |
|---|---|---|
| `apps/web` | React + Vite | Trace browsing, diagnosis interaction, findings board |
| `apps/server` | Fastify + TypeScript | HTTP API, ingestion, storage access, analysis orchestration |
| `packages/contracts` | TypeScript | Shared protocols and domain types across API and web |
| `research/` | Markdown + YAML | Evaluation tasks, harness adapters, experiment records |

The backend is a modular monolith, not microservices; split services only when independent scaling or isolation demands it.

## Vertical slices

```text
apps/server/src/
  app.ts                HTTP 组装入口
  sessions/             session 列表、详情、时间线
  ingest/               Codex rollout 扫描与解析
  storage/              repository 接口与 SQLite 实现
  analysis/             规则诊断、AI 诊断、分析任务
```

Slices collaborate through explicit interfaces; routes are registered only in `app.ts`, so feature entry points never scatter.

## Data flow

```text
~/.codex/sessions/**/*.jsonl
        │
        ▼
  ingest 解析与归一化
        │
        ▼
  SQLite（raw_records / sessions / turns / items）
        │
        ├──► REST API ──► Web 时间线
        │
        └──► analysis worker ──► findings ──► Web 问题看板
```

Raw records and normalized views are stored separately: parser upgrades can replay without rereading the user's directory.

## Data-layer strategy

- Start with SQLite, keep the database file under `data/`, and never commit it.
- Business code depends only on repository interfaces and never concatenates SQL.
- Keep schemas portable and avoid SQLite-specific types; migrations are versioned.
- Switching to Postgres replaces repository implementations and migrations without changing the API contract.
- Ingestion must be idempotent: rescanning the same rollout creates no duplicate session or turn.

## API draft

```text
GET  /api/health
GET  /api/sessions
GET  /api/sessions/:id
GET  /api/sessions/:id/timeline
POST /api/ingest
POST /api/sessions/:id/analyze
GET  /api/analyses/:id
```

Only `GET /api/health` exists today. Later endpoints change `packages/contracts` first, then the server; the web app never copies field definitions.

## Shared contract

The health response is the first contract sample across both ends:

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export interface HealthResponse {
  ok: boolean;
  service: "harness-evolution";
  phase: ServicePhase;
}
```

The type fence is compared verbatim with source by `verify-type-equiv`; contract drift turns red.

Minimal web-side contract usage (compiled for real by `doc-typecheck`):

```ts
import type { HealthResponse } from "./packages/contracts/src/index";

const health: HealthResponse = {
  ok: true,
  service: "harness-evolution",
  phase: "scaffold",
};
```

## Current state and non-goals

- Present: workspace, web shell, server shell, shared contract, health check.
- Missing: database, migrations, trace parsing, diagnosis, model calls, user system.
- Explicitly out: multi-tenancy, permissions, production credentials, automatic code changes without evaluation evidence.
