# Agent Note: FastAPI service boundary

Status: implemented

English | [中文](2026-10-24-fastapi-service-boundary.md)

## Problem

The TypeScript/Fastify shell served only a health check, yet diverged from the target SaaS stack for Python data processing, jobs and OpenAPI contracts. Layering more work onto that shell would combine framework migration with business integration risk and leave docs, CI and local commands pointing at an implementation scheduled for removal.

## Decision

- Replace the backend with a Python 3.12 + FastAPI modular monolith under `apps/api`, split into `api/service/db/third_party_api`, with routes registered only in `main.py`.
- Load configuration from the `HE_` environment namespace; keep the health check public and return `phase=scaffold`.
- Control API documentation and OpenAPI with `HE_DOCS_ENABLED`; development enables both by default and production deployments explicitly disable them.
- Return `{error:{code,message,details}}` for expected failures, unknown routes, validation failures and uncaught exceptions; expose only the request ID for unexpected errors.
- Until identity lands, a boundary middleware returns `401 AUTH_REQUIRED` for non-public `/api/*` paths so business routes cannot accidentally open unauthenticated.
- Manage Python dependencies with `venv + pip` and expose pnpm wrapper commands from the repository root; CI runs ruff, mypy, pytest and coverage on Python 3.12.
- Delete the `apps/server` Fastify shell so two backends do not coexist.

## Alternatives considered

- Keep building on Fastify and migrate all at once later: database and feature slices would first depend on a framework slated for replacement, expanding rollback scope; rejected.
- Add the database, identity and business routes immediately: m1-02 would lose independent acceptance and mix platform risk with feature defects in one PR; rejected.
- Leave non-public APIs open temporarily: that creates a fail-open security debt before identity exists; rejected.
- Add the Python backend to the pnpm workspace: pnpm does not manage Python dependencies and would create a false single-package-manager boundary; rejected.

## Consequences

- Local and CI environments must create a Python 3.12 venv first; root pnpm wrappers keep command entry points consistent.
- m1-06 must replace the temporary identity boundary rather than append identity after it; otherwise every path except health would remain 401.
- The unified error envelope becomes a stable input for the web interceptor and future generated OpenAPI contracts.
- The React web shell remains until m1-05 switches it to Vue; this slice replaces only the backend boundary.
