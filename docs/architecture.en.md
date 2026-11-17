# Architecture

English | [中文](architecture.md)

Records service boundaries, data flow and storage; slice rationale lives in `.agents/notes/`.

## Product boundary

Contains workspaces and members, credential ingest, fixtures/local import, normalization, the Agent tree, workspace Sessions and overview, multi-attribution error details, seven-step evolution and the lane DAG. V1 read endpoints and workspace-less routes remain in the compatibility window; see [compatibility.en.md](compatibility.en.md).

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

Only health, login, refresh, the IdP callback, ticket SSE, and credential ingest are public; everything else uses a bearer JWT, and workspace creation, user management, sync, and upstream pull are global-admin only. Access lasts 30 minutes; the refresh cookie lasts 14 days with httpOnly, SameSite=Strict; authentication and failures share one boundary.

Web restores `auth/session` before mounting routes; tokens and users stay in memory, concurrent 401s share one refresh, and logout clears the query cache. Pages live under `/workspaces/:wid` and scope every resource by `wid` and member role; `/`, `/sessions/**`, `/errors`, and `/evolution/**` redirect to the remembered visible workspace, the only visible workspace, or the chooser.

The session page uses a 360px list plus overview, defaults to the latest 10 and searches on Enter; error details group by case with `case/tab/at` deep links; target configuration and the wizard are workspace-scoped, run details use seven steps, and lifespan recovers jobs and `sync_lock` before scheduling.

A trace that is not ready is not a 404.

## Data-layer strategy

- Production MySQL 8, local/test SQLite; `HE_DB_DIALECT` is the only selection point. `Database` owns connections, read sessions, write transactions, and health; Alembic maintains dual-dialect migrations, and business code depends only on `db/crud/` and `Database`.
- Workspaces: `workspaces`, `workspace_members`, `workspace_ingest_credentials`; bad cases, target configuration, and runs carry `workspace_id`. Traces are global, and workspace Sessions are projected from bad cases.
- Ingest: a credential writes only the URL workspace, quota is checked inside the write transaction, and re-reporting an ID upserts idempotently without double counting.
- Attribution: `bad_case_analysis` links multiple rows by `(bad_case_id, probe_id)`; `probe_reports` stores the conclusion, cache key, and reuse count; the cache key covers workspace, case, object identity, version, policy, and engine.
- Evidence: parent/child relations are `authoritative/derived/synthetic/unresolved`; `execution_outcome` is independent of parse status; object revision comes from `path + body hash` or a tag, and an unknown revision is never guessed by name.
- Knowledge triggers: `kind=knowledge` accepts only documents under a workspace knowledge root or returned by a knowledge Provider/Collection, storing `document_id`, revision, source path, retrieval kind, and tool_use, never the body.
- Jobs: `job_runs` is the task source of truth; a serial worker writes run events, the bus sends bounded notifications, and `sync_lock` is single-flight with the job in one transaction, so an abnormal `sync_runs` finalizes before the lock is released; raw payloads are unique by `(runtime_key, root_session_id, agent_id)`, fixtures seed the same tables idempotently, and replay assembles atomically per root before one transactional rewrite.
- Upstream uses a versioned outbound contract; pull writes `http_api` payloads before shared replay; normalization picks a parser subclass by runtime through `TraceParserFactory`, keeping messages and content out of storage.
- Compatibility: unprefixed read endpoints filter by the union of visible workspaces; V1 runs are read-only mapped to seven steps; `bad_case_analysis.probe_id` and `probe_reports.cache_key` stay nullable. Deletion conditions live in [compatibility.en.md](compatibility.en.md).
- Secrets enter only through environment variables, never the repo or database.

## Shared contract

FastAPI OpenAPI is the sole inbound contract source; the upstream query exports an independent JSON Schema and fixture through strict Pydantic models, and `contract:check` rejects drift in both snapshots.

The health response makes API and database state independently observable:

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];
```

## State and boundaries

- Present: dual-dialect API, authentication and workspace roles, credential ingest and quota, workspace Session and overview, multi-attribution error details, four-step wizard, seven-step runs and lane DAG, evidence gates and knowledge triggers, jobs/SSE, target configuration, fixtures, cross-stack API/E2E, and docs/flow/contract gates.
- Missing: real evaluation and patches, a real clustering algorithm, and user deactivation UI.
- Explicitly out: production credential access, automatic code changes without evidence, and deleting V1 surfaces inside the compatibility window.
