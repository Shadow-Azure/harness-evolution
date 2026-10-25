# m1-04 implementation report

## Status

Implemented on `codex/m1-04-contract-pipeline`.

## Requirement mapping

- FastAPI OpenAPI is exported deterministically to `packages/contracts/openapi.json`.
- `openapi-typescript` generates `packages/contracts/src/generated/api.d.ts` with an `@generated` marker.
- `packages/contracts/src/index.ts` aliases generated health, database, phase, dialect and error types; prototype-only session types remain local until m1-05.
- `contract:check` renders the snapshot and generated file in a temporary directory and compares both without touching the worktree.
- CI runs `contract:check` before the build; route gates route API, contract and web changes to the check.
- Backend snapshot tests, frontend generated-type tests, existing cross-stack health/503/401 integration, and both 80% coverage floors remain enforced.

## TDD evidence

- RED: `test_openapi.py` failed because the snapshot was absent and FastAPI did not publish `ErrorResponse`/`ErrorBody`.
- RED: `gates.spec.mjs` failed while importing the missing contract generator and while asserting route/CI wiring.
- GREEN: added the error response documentation, deterministic exporter, generator/check script, generated artifacts, contract aliases, and gate wiring.

## Verification

- `pnpm contract:check` — passed.
- `pnpm test` — frontend 30 passed / 1 skipped; backend 32 passed / 3 MySQL-only skipped, 93% coverage.
- `pnpm test:db` — 10 passed.
- `pnpm test:integration` — 3 passed with sandbox-external loopback authorization.
- `pnpm test:gates` — 20 passed.
- `pnpm lint:api`, `pnpm typecheck`, `pnpm build`, `pnpm verify:flow`, `pnpm verify:docs` — passed.
- Frontend coverage from `pnpm test`: statements 97.11%, branches 84.53%, functions 100%, lines 97.11%.

## Deviations and risks

- The local host uses Python 3.14; the repository and CI remain pinned to Python 3.12.
- MySQL execution remains a CI service lane rather than a local prerequisite.
- OpenAPI generation uses the existing health/error DTOs only; business endpoints remain unimplemented by design.
