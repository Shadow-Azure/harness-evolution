# Architecture

English | [中文](architecture.md)

Records service boundaries, data flow and storage; slice rationale lives in `.agents/notes/`.

## Product boundary

The service contains fixtures, local import, JSONL normalization, Agent-tree assembly, session queries, read-only problem attribution queries, and error-detail browsing.

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

Only health, login, refresh, and ticket-authenticated SSE are public; other APIs require bearer JWTs, and `/api/users`, manual sync, and upstream pull are admin-only. Access lasts 30 minutes; the refresh cookie lasts 14 days with `httpOnly`, `SameSite=Strict`, `/api/auth` scope, and production `Secure`; authentication and failures share one boundary.

Web restores the session before mounting routes; tokens and users stay in memory. Guards handle login and forced password change, concurrent 401s share one refresh, and logout clears the query cache.

The session page uses a 360px list plus overview. Search, status, sort, selection, and evidence live in the URL.

Target configuration is member-readable and admin-writable; it includes disabled rows, the wizard catalog includes enabled rows only, and the backend owns errors.

Run lists are backend-grouped with backend-generated display facts.

Error details combine a problem sidebar, execution flow and two tabs; selection lives in the URL, cross-session ownership returns 409, panels remember scroll offsets, and asynchronous flow remains subject to bundle and performance gates.

The lifespan recovers jobs and `sync_lock` before scheduling; manual and timed triggers share the single-flight lock, and no pending work creates no job.

## Data-layer strategy

- Production uses MySQL 8 while fast local runs and automated tests use SQLite; `HE_DB_DIALECT` is the only selection point.
- The `Database` interface owns connection lifecycle, read sessions, write transactions and health; `api/service` code never creates engines directly.
- Alembic maintains one dual-dialect tree; business code depends on `db/crud/` and `Database` and never concatenates SQL.
- `job_runs` is the task source of truth; a serial worker writes run-scoped `evolution_run_events`, the event bus carries bounded notifications, and interruptions persist first.
- Evolution: `progress_unit`/`EngineFactory`, admin targets, git refs/tags, and `agents.model`.
- `sync_lock` is the single-flight source; job and lock share one transaction, and abnormal `sync_runs` finalize before the matching lock is released. Restart recovery retains the interrupted audit and uses a fresh replay run id.
- Raw payloads are uniquely stored by `(root_session_id, agent_id)`; fixtures idempotently seed the same tables.
- Upstream uses a versioned outbound contract; pull writes `http_api` payloads before shared replay. CI uses mock transport only.
- Normalization parses each payload independently, keeps messages and content blocks in memory, and emits user-input anchors, Agent/Skill/Workflow triggers, and statistics.
- Replay is atomic per root: assemble, then transactionally rewrite and advance source cursors.
- External problem tables are read-only.
- Secrets enter only through environment variables, never repo or database.

## Shared contract

FastAPI OpenAPI is the sole contract source for inbound APIs covering health, identity, users, sessions, jobs, acquisition, and events. The upstream query is a client-side outbound contract whose strict Pydantic models export an independent JSON Schema and fixture snapshot. `contract:check` compares both byte-for-byte to reject drift.

The health response makes API and database state independently observable:

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];
```

## State and boundaries

- Present: dual-dialect API, identity, jobs/SSE, session queries, problem/attribution APIs, error details, sync/upstream pull, external issue models, target configuration, evolution run/detail/event logs (six steps, workspace, blocked/retry/eval, real lastEventSeq), real prepare/Git candidates, placeholder evaluation closure and automatic recovery, launch/preview and read-only step APIs, fixtures, data chains, E2E, and contract gates.
- Missing: real evaluation, real patches, and user deactivation UI.
- Explicitly out: multi-tenancy, production credential access and automatic code changes without evaluation evidence.
