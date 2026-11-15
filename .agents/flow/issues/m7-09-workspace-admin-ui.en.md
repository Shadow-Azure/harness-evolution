# Workspace management and ingest UI

English | [中文](m7-09-workspace-admin-ui.md)

```yaml flow
kind: issue
id: m7-09
milestone: m7
depends:
  - m7-05
  - m7-08
priority: P1
status: in-progress
scope:
  - apps/web/src/pages/workspaces/**
  - apps/web/src/api/**
  - apps/web/src/composables/**
  - apps/web/src/stores/**
  - apps/web/src/router/**
  - apps/web/src/router.test.ts
  - apps/web/src/components/**
  - apps/web/src/components.d.ts
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/implemented/feature/2026-11-15-workspace-admin-ui.md
github:
  number: 230
  url: https://github.com/Shadow-Azure/harness-evolution/issues/230
```

## Background

Admins need UI for spaces, quota, members, and ingest credentials.

## Goals

- Implement four admin tabs.
- Mirror server authority.
- Show plaintext credentials once.

## Design authority

- [08 §4.2](../../../plans/fullstack-design/08-frontend-implementation.md)：空间管理页。
- [design-v2.md §3–§4](../../../plans/ui-prototype-v2/design-v2.md)：原型验收。

## Implementation

- Add space create and quota forms.
- Add candidate search and role controls.
- Add credential rotation UI.

## Implementation steps

1. Write visibility tests.
2. Implement tabs.
3. Add E2E coverage.

## Dependencies and boundary

- Dependencies: m7-05, m7-08
- Boundary: no overview.

## Verification

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern workspace-admin
```

- Writes stay hidden when unauthorized.
- Locked roles cannot change.
- Credentials cannot be reread.

## Acceptance

- The prototype IA is met.
- Server checks remain authoritative.

## Gates and CI

- Web, E2E, contract, and flow gates.

## Non-goals

- No global directory.
- No registration or extra admin.
