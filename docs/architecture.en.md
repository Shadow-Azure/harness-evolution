# Architecture

English | [中文](architecture.md)

Records current service boundaries, data flow and storage strategy. Implementation advances by vertical slices; rationale lives in `.agents/notes/`.

## Product boundary

This trace-diagnostics service currently delivers only the M1 platform foundation; trace, problem and evolution data are not yet in the runtime path.

## Service split

| Unit | Technology | Responsibility |
|---|---|---|
| `apps/api` | Python 3.12 + FastAPI | HTTP API, service orchestration, storage and third-party boundaries |
| `apps/web` | React + Vite | Current development shell; M1 later switches to Vue 3 |
| `packages/contracts` | TypeScript | Shared protocols and domain types for the web app |
| `research/` | Markdown + YAML | Evaluation tasks, harness adapters and experiment records |

Routes are registered only in `apps/api/app/main.py`; HTTP handles validation and identity, business rules live in `service/`, and storage and integrations are isolated in `db/` and `third_party_api/`.

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

Dependency direction is `api → service → db/third_party_api`.

## Current request path

```text
Web ──► FastAPI middleware ──► api/health
                     │
                     └──► non-public /api/* → 401 AUTH_REQUIRED
```

`/api/health` is public and returns `ok/service/phase/version/db`; database failure returns 503 while the process stays reachable. Other `/api/*` paths default to 401; unknown routes, validation failures and uncaught exceptions share one error envelope.

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

FastAPI OpenAPI is the sole contract source. The export script writes the deterministic `packages/contracts/openapi.json` snapshot, and `openapi-typescript` derives `packages/contracts/src/generated/api.d.ts` from it; `src/index.ts` exposes only stable aliases and cross-end constants. `contract:check` regenerates in a temporary directory and compares byte for byte, so hand edits or backend drift fail before the build.

The health response is the current minimal contract between both ends, with API and database state independently observable:

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];
```

The type fence is structurally compared with source by `verify-type-equiv`; generated-type drift is blocked by `contract:check`.

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

- Present: modular FastAPI scaffold, unified error model, SQLite/MySQL Database boundary, Alembic baseline, health check, OpenAPI contract generation and drift prevention, and Python lint/type/test gates.
- Missing: domain tables, real identity, trace parsing, problem queries and evolution execution.
- Explicitly out: multi-tenancy, production credential access and automatic code changes without evaluation evidence.
