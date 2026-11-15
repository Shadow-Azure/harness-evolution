# AuthProvider seam and single-admin boundary

English | [中文](m7-04-auth-provider-seam.md)

```yaml flow
kind: issue
id: m7-04
milestone: m7
depends:
  - m7-02
  - m7-03
priority: P0
status: in-progress
scope:
  - apps/api/app/service/identity/**
  - apps/api/app/api/auth.py
  - apps/api/app/api/users.py
  - apps/api/app/config.py
  - apps/api/app/errors.py
  - apps/api/app/db/crud/users.py
  - apps/api/app/db/models/users.py
  - apps/api/app/middleware/auth.py
  - apps/api/app/middleware/rate_limit.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - deploy/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/implemented/architecture/2026-11-15-auth-provider-seam.md
github:
  number: 225
  url: https://github.com/Shadow-Azure/harness-evolution/issues/225
```

## Background

Future Cookie or SSO integration should replace identity plumbing without changing business authorization.

## Goals

- Add AuthProvider and callback seams.
- Keep one global admin and no registration.
- Never auto-create mapped users.

## Design authority

- [07 §8.2.1](../../../plans/fullstack-design/07-backend-implementation.md)：AuthProvider 接缝。
- [05 §4.16](../../../plans/fullstack-design/05-api-design.md)：鉴权端点与错误码。

## Implementation

- Keep the password provider.
- Fail fast for unimplemented providers.
- Cover callback error codes.
- A public callback, stable error codes, and startup validation touch API wiring, error codes, middleware, and API tests, so the scope covers them; configuration notes, OpenAPI, and the Agent Note change in the same PR.

## Implementation steps

1. Write identity seam tests.
2. Split provider and bridge.
3. Update config and contracts.

## Dependencies and boundary

- Dependencies: m7-02, m7-03
- Boundary: seam only.

## Verification

```sh
pnpm test:api -- tests/identity; pnpm contract:check
```

- Password login does not regress.
- Invalid providers fail startup.
- Unconfigured callback returns 501.

## Acceptance

- Identity providers remain isolated.
- Only one global admin can exist.

## Gates and CI

- Identity, contract, and flow gates.

## Non-goals

- No live Cookie or SSO provider.
- No registration.
