# Architecture

English | [中文](architecture.md)

Records service boundaries, data flow and storage. Work advances by vertical slices; rationale lives in `.agents/notes/`.

## Product boundary

The service contains M1/M2 fixtures, local import, and per-payload JSONL normalization; Agent-tree assembly and session queries are not running yet.

## Service split

| Unit | Technology | Responsibility |
|---|---|---|
| `apps/api` | Python 3.12 + FastAPI | HTTP API, service orchestration, storage and third-party boundaries |
| `apps/web` | Vue 3 + Vite | Routing, shared data access, and progressively loaded business pages |
| `packages/contracts` | TypeScript | Shared protocols and domain types for the web app |
| `research/` | Markdown + YAML | Evaluation tasks, harness adapters and experiment records |

Routes are registered only in `apps/api/app/main.py`; dependency direction is `api → service → db/third_party_api`.

## Vertical slices

```text
main.py
api/
service/
db/
third_party_api/
middleware/
```

## Current request path

```text
Web ──► middleware ──► public endpoints | bearer APIs | ticket-authenticated SSE → api routers
```

Only health, login, refresh, and ticket-authenticated SSE are public; other APIs require bearer JWTs, and `/api/users` is admin-only. Access lasts 30 minutes; the refresh cookie lasts 14 days with `httpOnly`, `SameSite=Strict`, `/api/auth` scope, and production `Secure`. Login is IP-limited, forced password change exposes only required endpoints, and failures share one envelope.

Web restores the session before mounting routes; tokens and users stay in memory. Guards handle login and forced password change; concurrent 401s share one refresh and each request replays once; logout clears the query cache.

## Data-layer strategy

- Production targets MySQL 8 while fast local runs and automated tests use SQLite; `HE_DB_DIALECT` is the only selection point.
- The `Database` interface owns connection lifecycle, read sessions, write transactions and health; `api/service` code never creates engines directly.
- Alembic maintains one dual-dialect migration tree with batch mode for SQLite changes; business code depends on `db/crud/` repositories and never concatenates SQL directly.
- `job_runs` is the task source of truth; a serial worker writes run-scoped `evolution_run_events`, the event bus carries bounded notifications, and interruptions persist first.
- Raw payloads are uniquely stored by `(root_session_id, agent_id)`; fixtures idempotently seed the same tables.
- Normalization parses each payload independently, keeps messages and content blocks in memory, and emits user-input anchors, Agent/Skill/Workflow triggers, and statistics.
- Local import reads only JSONL/metadata, transactionally writes payloads and unprocessed indexes, preserves runtime state on re-import, and ignores other local state.
- External systems write problems and attribution; this service reads only.
- Secrets enter only through environment variables, never repo or database.

## API

```text
GET /api/health
POST /api/auth/{login,refresh,logout,change-password}
GET /api/auth/me
GET|POST /api/users
GET /api/jobs/{jobId}
POST /api/events/ticket
GET /api/events?ticket=…
```

SSE tickets bind the user, topics, and cursor, use HMAC with a 60-second expiry, and allow one consumption. A connection pages history before live events, emits `ping` while idle, and emits `reset` for a stale cursor. An injectable authorizer checks run topics; refresh rotation rejects replay, and timestamps use Asia/Shanghai.

## Shared contract

FastAPI OpenAPI is the sole contract source. The exported snapshot drives generated types; `src/index.ts` exposes only stable aliases and constants. `contract:check` regenerates and compares bytes, so drift fails before build.

The health response makes API and database state independently observable:

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];
```

## State and boundaries

- Present: dual-dialect API, identity, jobs/SSE, three-entry shell, fixtures/seed, local import, E2E, and contract gates.
- Missing: Agent-tree assembly/session queries, issue queries, evolution execution, run authorization, and user deactivation UI.
- Explicitly out: multi-tenancy, production credential access and automatic code changes without evaluation evidence.
