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

Health, login, refresh, the IdP callback, ticket SSE, and credential ingest are public; everything else uses a bearer JWT, and global writes require an administrator. Access lasts 30 minutes; refresh lasts 14 days with httpOnly, SameSite=Strict, and protocol/configured Secure; authentication errors share one boundary.

Web restores `auth/session` first; identity stays in memory, concurrent 401s share one refresh, and logout clears caches. Pages under `/workspaces/:wid` scope resources by workspace and role; unscoped routes redirect to the remembered workspace, sole workspace, or chooser.

Sessions default to the latest 10 and search on Enter; errors group by case with `case/tab/at` deep links; targets and the wizard are workspace-scoped, and seven-step runs show the frozen revision; lifespan recovers jobs and `sync_lock` before scheduling.

A trace that is not ready is not a 404.

## Data-layer strategy

- Production MySQL 8, local/test SQLite; `HE_DB_DIALECT` is the only selection point. `Database` owns connections, read sessions, write transactions, and health; Alembic maintains dual-dialect migrations, and business code depends only on `db/crud/` and `Database`.
- Workspaces: `workspaces`, `workspace_members`, `workspace_ingest_credentials`; bad cases, target configuration, and runs carry `workspace_id`. Traces are global, and workspace Sessions are projected from bad cases.
- Ingest: a credential writes only the URL workspace, quota is checked inside the write transaction, and re-reporting an ID upserts idempotently without double counting.
- Each target binds one workspace Skill, initially `attribute-badcases`. Saving a binding schedules background attribution. The wizard reuses the latest report per case and target revision or selects a Skill for this run. `HE_ATTRIBUTION_AGENT=claude` selects the local CLI and `HE_ATTRIBUTION_MODEL` selects its model. The [attribution workspace](../attribute/README.en.md) stores Skills, target definitions, attribution inputs and reports. The worker validates the platform writer’s output, writes V2 with the original report to `probe_reports`, and links the candidate transactionally.
- External problem tables follow the 06 §4 contract; schema/row drift emits structured logs, read failures map to stable codes, and the path issues SELECT only.
- Evidence: parent/child relations are `authoritative/derived/synthetic/unresolved`; `execution_outcome` is independent of parse status; object revision comes from `path + body hash` or a tag, and an unknown revision is never guessed by name.
- Knowledge triggers: `kind=knowledge` accepts only workspace-root or Provider/Collection documents and stores identity, revision, source, and retrieval evidence, never the body.
- Jobs: `job_runs` is the source of truth. Work is serial by default; attribution uses a bounded claim/lease lane, and four entrypoints share one idempotent service. `sync_lock` and its job are transactional single-flight; payload triples are unique, and replay rewrites each root atomically.
- Upstream uses a versioned outbound contract; pull writes `http_api` payloads before shared replay; normalization selects a session parser by trace shape through `can_parse` / `TraceParserFactory.for_trace` and produces links, keeping messages and content out of storage.
- Compatibility: unprefixed reads use visible-workspace union; V1 runs map read-only to seven steps; legacy nullable fields and deletion conditions live in [compatibility.en.md](compatibility.en.md).
- Secrets enter only through environment variables, never the repo or database.

## Shared contract

FastAPI OpenAPI is the sole inbound contract source; the upstream query exports an independent JSON Schema and fixture through strict Pydantic models, and `contract:check` rejects drift in both snapshots.

The health response makes API and database state independently observable:

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];
```

## State and boundaries

- Present: API, authentication and workspace roles, credential ingest and quota, workspace Session and overview, multi-attribution error details, four-step wizard, seven-step runs and lane DAG, evidence gates and knowledge triggers, jobs/SSE, target configuration, fixtures, cross-stack API/E2E, and docs/flow/contract gates.
- Missing: real evaluation and patches, and user deactivation UI.
- Explicitly out: production credential access, automatic code changes without evidence, and deleting V1 surfaces inside the compatibility window.
