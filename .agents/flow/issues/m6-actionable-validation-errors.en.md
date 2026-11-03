# Actionable validation errors with fix guidance

English | [中文](m6-actionable-validation-errors.md)

```yaml flow
kind: issue
id: m6-21
milestone: m6
depends: []
priority: P1
status: ready
scope:
  - apps/api/app/errors.py
  - apps/api/app/api/**
  - apps/web/src/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 191
  url: https://github.com/Shadow-Azure/harness-evolution/issues/191
```

## Background

Session filtering, session sync, the evolution wizard, run retry, and target configuration all trigger API or domain validation. Some pages currently show `request validation failed`, an English backend phrase, or one generic failure line, so users cannot tell which input exceeded a rule, which operation lacked permission, whether a resource conflicts, or what to change next.

The backend already returns stable `code` and `details` in the unified error envelope, but the frontend has no shared actionable-presentation layer; individual catch blocks fall back to short copy, producing inconsistent 422 quality across interactions.

## Goals

- Provide one shared API-error formatter that prefers stable codes, field paths, and validation details to produce operation-specific copy.
- Map common 422 validation failures to Chinese reasons and fixes; when details are absent, retain a clear scenario copy and retry guidance instead of exposing internal English phrases or stacks.
- Validate login/password change, the evolution wizard, run retry, and target save in the same pass with readable, locatable failures.
- Keep `ApiError.details` presentation sanitized; never reveal submitted content, internal paths, credentials, or server stacks.

## Design authority

- [05 API design §4.1](../../../plans/fullstack-design/05-api-design.md): unified response and error envelope contract.
- [08 frontend implementation §2.2](../../../plans/fullstack-design/08-frontend-implementation.md): `api/http.ts` owns `ApiError` and unified error-detail transport.
- [08 frontend implementation §9](../../../plans/fullstack-design/08-frontend-implementation.md): evolution wizard pre-validation and failure handling policy.

## Implementation

- Add `formatApiError` / `formatValidationDetails` presentation helpers that synthesize field-level reasons and fixes from `code`, `status`, and `details.errors[].loc/msg/type`.
- Extend the global query fallback beyond 409 so 422 and business errors use the same formatter; retain page-specific stable-code branches where they already exist.
- Replace raw `error.message` presentation in target save, the wizard, run retry, and login/password change with the shared formatter.
- Keep `loc/msg/type` in FastAPI `RequestValidationError` details and add safe field-path semantics; contract changes remain additive.
- Add frontend unit tests for formatting and key page failure states, plus API integration assertions for the 422 envelope.

## Implementation steps

1. Add failing tests for shared formatting across validation details, no details, network, permission, conflict, and server failures.
2. Implement the shared formatter and connect the global query fallback plus target save, wizard, run retry, and login/password change pages.
3. Add FastAPI 422 response assertions and regenerate contracts when needed.
4. Run frontend/backend lint, typecheck, focused tests, contract checks, and flow/docs gates.

## Dependencies and boundary

- 依赖：无
- 非目标：<待补>
- Delivery boundary: unify presentation semantics for the existing error envelope; do not refactor page architecture, change stable error codes, or add external dependencies.
- Compatibility: old responses without `details` must fall back; `#185` remains the target-specific deep diagnosis slice.

## Verification

```sh
pnpm test:api -- tests/api
pnpm --filter @harness/web exec vitest run src/app src/pages/evolution src/pages/login
pnpm lint:api
pnpm lint:web
pnpm typecheck:api
pnpm typecheck:web
pnpm contract:check
pnpm verify:flow
pnpm verify:docs
```

- A 422 fixture returns field location, a Chinese reason, and a fix; a response without details falls back to “check the input and retry”.
- 500, 403, 409, and network failures show wait/contact, permission, conflict, and network guidance without internal English phrases.
- Page tests prove failures appear in the relevant interaction area and no longer show raw `request validation failed`.

## Acceptance

- Every key interaction's validation failure states what happened, which input or operation needs correction, and the recommended next step.
- 422 field paths map to user-readable labels; unknown paths still receive a generic input-check recommendation.
- Shared formatter branches are covered by the existing frontend gate, and all added or updated tests pass.

## Gates and CI

- API/web lint, typecheck, unit tests, and contract checks run in CI; coverage remains at or above 80%.
- `verify:flow --diff main` requires the remote issue number in the PR title and keeps the diff within scope.

## Non-goals

- Do not expose raw exceptions, stacks, server paths, or request bodies to users.
- Do not implement git-output diagnosis for `REPO_INVALID`; `#185` owns that work.
- Do not add a global modal that intercepts every error; inline errors and active-operation context take priority.
