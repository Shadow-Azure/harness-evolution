# Architecture

English | [中文](architecture.md)

Records current service boundaries, data flow and storage strategy. Implementation advances by vertical slices; rationale lives in `.agents/notes/`.

## Product boundary

This trace-diagnostics service currently delivers only the M1 platform foundation; trace, problem and evolution data are not yet in the runtime path.

## Service split

| Unit | Technology | Responsibility |
|---|---|---|
| `apps/api` | Python 3.12 + FastAPI | HTTP API, service orchestration, storage and third-party boundaries |
| `apps/web` | Vue 3 + Vite | Routing, shared data access, and progressively loaded business pages |
| `packages/contracts` | TypeScript | Shared protocols and domain types for the web app |
| `research/` | Markdown + YAML | Evaluation tasks, harness adapters and experiment records |

Routes are registered only in `apps/api/app/main.py`; HTTP handles validation and identity, business rules live in `service/`, and storage and integrations are isolated in `db/` and `third_party_api/`.

## Vertical slices

```text
main.py
api/
service/
db/
third_party_api/
middleware/
```

Dependency direction is `api → service → db/third_party_api`.

## Current request path

```text
Web ──► middleware ──► public endpoints | bearer APIs → api routers
```

Only health, login and refresh are public; business APIs read bearer JWTs, `/api/users` is admin-only, and OpenAPI declares protected operations with `BearerAuth`. Login is limited to 10 attempts per IP per minute, and forced password change permits only password change, logout and current identity. Access tokens last 30 minutes; the refresh cookie lasts 14 days with `httpOnly`, `SameSite=Strict`, `/api/auth` scoping, and `Secure` in production. Health returns 503 on database failure, and every failure shares one error envelope.

## Data-layer strategy

- Production targets MySQL 8 while fast local runs and automated tests use SQLite; `HE_DB_DIALECT` is the only selection point.
- The `Database` interface owns connection lifecycle, read sessions, write transactions and health; `api/service` code never creates engines directly.
- Alembic maintains one dual-dialect migration tree with batch mode for SQLite changes; business code depends on `db/crud/` repositories and never concatenates SQL directly.
- Raw trace payloads are replayable and idempotent; external systems write problems and attribution, which this service reads.
- Secrets enter only through environment variables, never the repository or database.

## Current API

```text
GET /api/health
POST /api/auth/{login,refresh,logout,change-password}
GET /api/auth/me
GET|POST /api/users
POST /api/events/ticket
```

SSE comes later; tickets bind the user, `run:{rid}` topics and cursor, authenticating 60-second expiry with a process HMAC while active grants remain single-use. Refresh rotation atomically rejects concurrent replay, and revocations expire with their tokens. An empty database seeds a forced-password-change administrator from environment credentials. Password change must replace the current secret, validation errors omit submitted values, passwords use argon2id, responses exclude password material, and timestamps use Asia/Shanghai.

## Shared contract

FastAPI OpenAPI is the sole contract source. The exported snapshot drives generated types; `src/index.ts` exposes only stable aliases and constants. `contract:check` regenerates and compares bytes, so drift fails before build.

The health response makes API and database state independently observable:

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];
```

## Current state and non-goals

- Present: modular API scaffold, unified errors, dual-dialect database boundary, users migration, real identity, user APIs, SSE ticket issuance, health check, contract pipeline, and Python gates.
- Missing: business domain tables, SSE transport, a user-deactivation interface, trace parsing, problem queries and evolution execution.
- Explicitly out: multi-tenancy, production credential access and automatic code changes without evaluation evidence.
