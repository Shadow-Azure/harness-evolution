# Agent Note: OpenAPI contract generation and drift prevention

Status: implemented

English | [中文](2026-10-25-openapi-contract-pipeline.md)

## Problem

Handwritten frontend health and error types duplicate the same fields from FastAPI. When the backend adds an enum value, changes casing or adjusts the 503 schema, the TypeScript compiler cannot detect the drift and the frontend learns about the mismatch only at runtime.

## Decision

- FastAPI OpenAPI is the sole interface contract source. Export recursively sorts object keys and fixes JSON indentation so the repository stores a deterministic snapshot.
- `openapi-typescript` generates `packages/contracts/src/generated/api.d.ts` from that snapshot with an `@generated` marker; `src/index.ts` exports only stable aliases and cross-end constants.
- `contract:generate` updates the snapshot, API types, real health JSON, and typed fixtures. `contract:check` recomputes every artifact in a temporary directory and compares byte for byte without modifying the worktree; missing files, hand edits or backend drift fail with a regeneration command. The JSON fixture remains the cross-language record of the real response, while the TypeScript fixture removes literal widening from JSON imports.
- CI runs `contract:check` before the build, and route gates send API, shared-contract and web changes through the same check.

## Alternatives considered

- Continue handwriting frontend API types: inexpensive at first, but creates a second source of truth that requires manual synchronization; rejected.
- Read `/api/openapi.json` dynamically at runtime for types: TypeScript cannot use it at build time, and production would depend on exposing the docs endpoint; rejected.
- Regenerate in CI and run `git diff`: workable, but it dirties the worktree and makes snapshot versus generated-file failures harder to classify; replaced by temporary-directory comparison.

## Consequences

- API changes require `pnpm contract:generate`; `contract:check` blocks forgotten regeneration locally and in CI.
- Generated files are never edited directly. Contract fixes belong in FastAPI DTOs or the generator.
- Unimplemented endpoints do not leak into the contract; prototype-only session types remain until their API slice replaces them.
