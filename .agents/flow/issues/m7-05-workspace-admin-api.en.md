# Workspace admin, member, and ingest credential APIs

English | [中文](m7-05-workspace-admin-api.md)

```yaml flow
kind: issue
id: m7-05
milestone: m7
depends:
  - m7-03
  - m7-04
priority: P0
status: in-progress
scope:
  - apps/api/app/api/workspaces.py
  - apps/api/app/service/workspaces/**
  - apps/api/app/db/crud/workspaces.py
  - apps/api/app/main.py
  - apps/api/app/errors.py
  - apps/api/app/middleware/auth.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 226
  url: https://github.com/Shadow-Azure/harness-evolution/issues/226
```

## Background

Global admins create workspaces; space admins manage quota, members, and credentials.

## Goals

- Implement workspace, member, and self-admin APIs.
- Implement credential rotation.
- Enforce space_admin locking.

## Design authority

- [05 §4.16](../../../plans/fullstack-design/05-api-design.md)：空间管理端点。
- [07 §5.15](../../../plans/fullstack-design/07-backend-implementation.md)：成员与凭据规则。

## Implementation

- Require an initial space admin.
- Keep member candidates scoped.
- Store credential hashes only.

## Implementation steps

1. Write role and credential tests.
2. Implement service and routes.
3. Update contracts.

## Dependencies and boundary

- Dependencies: m7-03, m7-04
- Boundary: no ingest.

## Verification

```sh
pnpm test:api -- tests/workspaces; pnpm contract:check
```

- Role escalation returns 403.
- Last admin cannot be removed.
- Revoked credentials fail.

## Acceptance

- The permission matrix passes.
- Secrets are never persisted.

## Gates and CI

- API, contract, security, and flow gates.

## Non-goals

- No deletion or archive.
- No member history.
