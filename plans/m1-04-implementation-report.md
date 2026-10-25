# m1-04 implementation report

## Status

Implemented on `codex/m1-04-contract-pipeline`.

## Requirement mapping

- FastAPI OpenAPI is exported deterministically to `packages/contracts/openapi.json`.
- `openapi-typescript` generates `packages/contracts/src/generated/api.d.ts` with an `@generated` marker.
- The exporter masks all `HE_*` process variables and `.env` loading so canonical schema settings cannot inherit host configuration.
- Real FastAPI ASGI 200/503 health responses generate `packages/contracts/fixtures/health.json` and typed `src/generated/health-fixtures.ts`; web tests import that same fixture.
- `packages/contracts/src/index.ts` aliases generated health, database, phase, dialect and error types; prototype-only session types remain local until m1-05.
- `contract:check` renders the snapshot, generated types, and response fixtures in a temporary directory and compares all without touching the worktree.
- CI runs `contract:check` before the build; route gates route API, contract and web changes to the check.
- Backend snapshot tests, frontend generated-type tests, existing cross-stack health/503/401 integration, and both 80% coverage floors remain enforced.

## TDD evidence

- RED: `test_openapi.py` failed because the snapshot was absent and FastAPI did not publish `ErrorResponse`/`ErrorBody`.
- RED: `gates.spec.mjs` failed while importing the missing contract generator and while asserting route/CI wiring.
- RED: environment drift reproducibly changed `info.version`, health schema lacked stable required fields, JSON fixtures could not satisfy generated types, and missing/stale workflow tests initially failed before executable checker paths and real response fixtures were added.
- GREEN: added the error response documentation, deterministic exporter, generator/check script, generated artifacts, contract aliases, and gate wiring.

## Verification

- `pnpm contract:check` — passed.
- `pnpm test` — frontend 30 passed / 1 skipped; backend 33 passed / 3 MySQL-only skipped, 93% coverage.
- `pnpm test:db` — 10 passed.
- `pnpm test:integration` — 3 passed with sandbox-external loopback authorization.
- `pnpm test:gates` — 21 passed.
- `pnpm lint:api`, `pnpm typecheck`, `pnpm build`, `pnpm verify:flow`, `pnpm verify:docs` — passed.
- Frontend coverage from `pnpm test`: statements 97.11%, branches 84.53%, functions 100%, lines 97.11%.
- Computer Use smoke: 8/8 scenarios passed with real Chrome, Vite proxy, canonical-environment probe and controlled 503; evidence is in [`reports/2026-10-25/m1-04-contract-pipeline`](../reports/2026-10-25/m1-04-contract-pipeline/smoke-report.html).

## Deviations and risks

- The local host uses Python 3.14; the repository and CI remain pinned to Python 3.12.
- MySQL execution remains a CI service lane rather than a local prerequisite.
- OpenAPI generation uses the existing health/error DTOs only; business endpoints remain unimplemented by design.
