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
status: backlog
scope:
  - apps/api/app/service/identity/**
  - apps/api/app/api/auth.py
  - apps/api/app/config.py
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
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
