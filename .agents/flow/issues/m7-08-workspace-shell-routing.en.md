# Workspace shell, route guards, and cache isolation

English | [中文](m7-08-workspace-shell-routing.md)

```yaml flow
kind: issue
id: m7-08
milestone: m7
depends:
  - m7-04
  - m7-06
  - m7-07
priority: P1
status: in-progress
scope:
  - apps/web/src/**
  - packages/contracts/**
  - tests/e2e/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
  - reports/**
adr:
  - ../../notes/implemented/architecture/2026-11-15-workspace-shell-routing.md
github:
  number: 229
  url: https://github.com/Shadow-Azure/harness-evolution/issues/229
```

## Background

Every V2 page needs explicit workspace context.

## Goals

- Add workspace routing and chooser.
- Isolate caches on switch.
- Redirect legacy routes safely.

## Design authority

- [03 §5–§7](../../../plans/fullstack-design/03-frontend-architecture.md)：启动、路由和状态。
- [08 §1.4、§4.2](../../../plans/fullstack-design/08-frontend-implementation.md)：重定向与空间壳。

## Implementation

- Bootstrap from auth/session.
- Prefix query keys with workspaceId.
- Add the workspace picker.
- Review records and the integration smoke report live in plans/ and reports/, so the scope covers both trees.

## Implementation steps

1. Write guard tests.
2. Implement the shell.
3. Add E2E coverage.

## Dependencies and boundary

- Dependencies: m7-04, m7-06, m7-07
- Boundary: no admin tabs.

## Verification

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern workspace-shell
```

- Guards redirect correctly.
- No stale query hits.
- Deep links recover once.

## Acceptance

- All pages carry wid.
- No silent workspace selection.

## Gates and CI

- Web, E2E, and flow gates.

## Non-goals

- No V1 visual rewrite.
- No global cache reuse.
