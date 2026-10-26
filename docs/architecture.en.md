# Architecture

English | [中文](architecture.md)

Records service boundaries, data flow and storage. Work advances by vertical slices; rationale lives in `.agents/notes/`.

## Product boundary

The service contains fixtures, local import, JSONL normalization, Agent-tree assembly, and session queries.

## Service split

| Unit | Technology | Responsibility |
|---|---|---|
| `apps/api` | Python 3.12 + FastAPI | HTTP API, service orchestration, storage and third-party boundaries |
| `apps/web` | Vue 3 + Vite | Routing, shared data access, and progressively loaded business pages |
| `packages/contracts` | TypeScript | Shared protocols and domain types for the web app |

Routes are registered only in `apps/api/app/main.py`; dependency direction is `api → service → db/third_party_api`.

## Current request path

```text
Web ──► middleware ──► public endpoints | bearer APIs | ticket-authenticated SSE → api routers
```

Only health, login, refresh, and ticket-authenticated SSE are public; other APIs require bearer JWTs, and `/api/users`, manual sync, and upstream pull are admin-only. Access lasts 30 minutes; the refresh cookie lasts 14 days with `httpOnly`, `SameSite=Strict`, `/api/auth` scope, and production `Secure`. Login is IP-limited, forced password change exposes only required endpoints, and failures share one envelope.

Web restores the session before mounting routes; tokens and users stay in memory. Guards handle login and forced password change; concurrent 401s share one refresh and each request replays once; logout clears the query cache.

The session page uses a 360px list plus overview. Search, status, sort, selection, and evidence live in the URL; statistics and density read `/api/sessions`.

Agent flow loads lazily.

After migrations, the lifespan recovers JobRunner and adopts `sync_lock` before starting the scheduler. Manual and timed triggers share the single-flight lock; no pending work creates no job.

## Data-layer strategy

- Production targets MySQL 8 while fast local runs and automated tests use SQLite; `HE_DB_DIALECT` is the only selection point.
- The `Database` interface owns connection lifecycle, read sessions, write transactions and health; `api/service` code never creates engines directly.
- Alembic maintains one dual-dialect migration tree with batch mode for SQLite changes; business code depends on `db/crud/` repositories and never concatenates SQL directly.
- `job_runs` is the task source of truth; a serial worker writes run-scoped `evolution_run_events`, the event bus carries bounded notifications, and interruptions persist first.
- `sync_lock` is the single-flight source across trigger sources with a 30-minute TTL. Job and lock are created in one transaction; a terminal job finalizes abnormal `sync_runs` before releasing its matching lock. Restart recovery retains the interrupted audit and uses a fresh replay run id.
- Raw payloads are uniquely stored by `(root_session_id, agent_id)`; fixtures idempotently seed the same tables.
- Upstream trace queries use a separate versioned outbound contract. A pull job writes validated raw lines with the `http_api` source before entering the shared replay pipeline. Missing configuration is unavailable, and CI uses only mock transport.
- Normalization parses each payload independently, keeps messages and content blocks in memory, and emits user-input anchors, Agent/Skill/Workflow triggers, and statistics.
- Replay is atomic per root: assemble first, then transactionally rewrite and advance source cursors.
- External systems write problems and attribution; this service reads only.
- Secrets enter only through environment variables, never repo or database.

## Shared contract

FastAPI OpenAPI is the sole contract source for inbound APIs covering health, identity, users, sessions, jobs, acquisition, and events. The upstream query is a client-side outbound contract whose strict Pydantic models export an independent JSON Schema and fixture snapshot. `contract:check` compares both byte-for-byte to reject drift.

The health response makes API and database state independently observable:

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];
```

## State and boundaries

- Present: dual-dialect API, identity, jobs/SSE, sync scheduling/status, upstream mock contract and pull, light prototype shell, fixtures/seed, local import, Agent-tree assembly, idempotent replay, session list/overview/tree queries, E2E, and contract gates.
- Missing: issue queries, evolution execution, run authorization, and user deactivation UI.
- Explicitly out: multi-tenancy, production credential access and automatic code changes without evaluation evidence.
