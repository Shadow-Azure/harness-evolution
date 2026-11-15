# Workspace-scope session and bad-case read paths

English | [中文](m7-06-session-bad-case-workspace-scope.md)

```yaml flow
kind: issue
id: m7-06
milestone: m7
depends:
  - m7-03
  - m7-05
priority: P0
status: done
scope:
  - apps/api/app/api/sessions.py
  - apps/api/app/api/problems.py
  - apps/api/app/service/sessions/**
  - apps/api/app/service/problems/**
  - apps/api/app/db/crud/**
  - apps/api/app/main.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/implemented/architecture/2026-11-15-session-bad-case-workspace-scope.md
github:
  number: 227
  url: https://github.com/Shadow-Azure/harness-evolution/issues/227
```

## Background

Workspace isolation requires every session and problem read to be workspace-scoped.

## Goals

- Scope reads by workspace.
- Return 404 for invisible sessions.
- Keep one compatibility version.

## Design authority

- [06 §7.5](../../../plans/fullstack-design/06-database-design.md)：空间 Session 投影。
- [07 §5.15](../../../plans/fullstack-design/07-backend-implementation.md)：服务端空间边界。

## Implementation

- Add workspace-prefixed routes.
- Project sessions through workspace bad cases.
- Filter legacy routes by visible spaces.
- Registering the workspace routers touches API wiring, and the cross-workspace tests plus the review record need API tests and plans, so the scope covers those files.

## Implementation steps

1. Write cross-workspace tests.
2. Move service queries.
3. Update contracts.

## Dependencies and boundary

- Dependencies: m7-03, m7-05
- Boundary: no graph changes.

## Verification

```sh
pnpm test:api -- tests/sessions tests/problems; pnpm contract:check
```

- Cross-workspace access returns 404.
- Shared sessions expose only workspace cases.
- Legacy routes still work.

## Acceptance

- All reads enforce workspace scope.
- The projection matches the design.

## Gates and CI

- API, database, contract, and flow gates.

## Non-goals

- No latest-ten interaction.
- No workspace column on trace tables.
