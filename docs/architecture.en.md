# Architecture

English | [中文](architecture.md)

Records the current service boundaries, data flow and data-layer strategy. Implementation advances slice by slice; this page states the present, while rationale lives in `.agents/notes/`.

## Product boundary

Harness Evolution works with coding-agent traces to provide navigable session browsing, problem attribution and evolution runs. M1 currently delivers the platform foundation only; trace, problem and evolution data are not yet in the runtime path.

## Service split

| Unit | Technology | Responsibility |
|---|---|---|
| `apps/api` | Python 3.12 + FastAPI | HTTP API, service orchestration, storage and third-party boundaries |
| `apps/web` | React + Vite | Current development shell; M1 later switches to Vue 3 |
| `packages/contracts` | TypeScript | Shared protocols and domain types for the web app |
| `research/` | Markdown + YAML | Evaluation tasks, harness adapters and experiment records |

The backend is a modular monolith. Routes are registered only in `apps/api/app/main.py`; the HTTP layer handles validation, identity and responses, business rules live in `service/`, and storage and third parties are isolated in `db/` and `third_party_api/`.

## Vertical slices

```text
apps/api/app/
  main.py               FastAPI composition root
  api/                  domain routers
  service/              business rules and orchestration
  db/                   database and CRUD boundary
  third_party_api/      outbound API adapters
  middleware/           request context and identity boundary
```

Slices collaborate through explicit interfaces; dependency direction remains `api → service → db/third_party_api`.

## Current request path

```text
Web ──► FastAPI middleware ──► api/health
                     │
                     └──► non-public /api/* → 401 AUTH_REQUIRED
```

`/api/health` is public and returns `ok/service/phase/version/db`. A failed database check returns HTTP 503 while the API process stays reachable. Until identity lands, every other `/api/*` path fails closed; unknown routes, validation failures and uncaught exceptions share one error envelope.

## Data-layer strategy

- Production targets MySQL 8 while fast local runs and automated tests use SQLite; `HE_DB_DIALECT` is the only selection point.
- The `Database` interface owns connection lifecycle, read sessions, write transactions and health; `api/service` code never creates engines directly.
- Alembic maintains one dual-dialect migration tree; both empty SQLite and MySQL databases upgrade to head, with batch mode for SQLite changes.
- Business code depends on repository/Database interfaces and never concatenates SQL directly.
- Raw trace payloads are the source of truth; normalized data must be replayable and idempotent.
- External systems own problem and attribution writes; this service reads them.
- Secrets enter only through environment variables, never the repository or database.

## Current API

```text
GET /api/health
```

Other draft endpoints belong to later milestones and are not implemented.

## Shared contract

The health response is the current minimal contract between both ends, with API and database state independently observable:

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export interface HealthResponse {
  ok: boolean;
  service: "harness-evolution";
  phase: ServicePhase;
  version: string;
  db: DatabaseHealth;
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
  version: "0.1.0",
  db: {
    dialect: "sqlite",
    ok: true,
    latencyMs: 0.2,
  },
};
```

## Current state and non-goals

- Present: modular FastAPI scaffold, unified error model, SQLite/MySQL Database boundary, Alembic baseline, health check and Python lint/type/test gates.
- Missing: domain tables, real identity, trace parsing, problem queries and evolution execution.
- Explicitly out: multi-tenancy, production credential access and automatic code changes without evaluation evidence.
