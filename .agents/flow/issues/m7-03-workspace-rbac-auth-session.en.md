# Workspace RBAC and auth session aggregate

English | [中文](m7-03-workspace-rbac-auth-session.md)

```yaml flow
kind: issue
id: m7-03
milestone: m7
depends:
  - m7-02
priority: P0
status: in-progress
scope:
  - apps/api/app/api/**
  - apps/api/app/db/crud/workspaces.py
  - apps/api/app/service/workspaces/**
  - apps/api/app/service/identity/**
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
  number: 224
  url: https://github.com/Shadow-Azure/harness-evolution/issues/224
```

## Background

Authentication alone is insufficient; every business request must authorize the target workspace.

## Goals

- Add require_workspace_role.
- Aggregate user and workspaces in auth/session.
- Return 404 for invisible workspaces.

## Design authority

- [01 §4.4](../../../plans/fullstack-design/01-architecture.md)：鉴权与空间授权链路。
- [07 §5.15、§8.2.1](../../../plans/fullstack-design/07-backend-implementation.md)：权限依赖与会话聚合。

## Implementation

- Implement the role order.
- Let global admins pass while retaining real member rows.
- Batch usage and membership data.
- The repository lands at `app/db/crud/workspaces.py`; wiring (`main.py`, `errors.py`, `middleware/auth.py`), `apps/api/tests`, and the `plans/` review record stay in scope.

## Implementation steps

1. Write the permission matrix tests.
2. Implement repository and dependency.
3. Add the endpoint contract.

## Dependencies and boundary

- Dependencies: m7-02
- Boundary: no member writes or frontend shell.

## Verification

```sh
pnpm test:api -- tests/workspaces tests/identity; pnpm contract:check
```

- The complete role matrix passes.
- Invisible spaces return 404.
- Session truncation is correct.

## Acceptance

- Business endpoints can share one guard.
- Users see only their spaces.
- Global admins see all spaces.

## Gates and CI

- API, contract, and flow gates.

## Non-goals

- No workspace roles in JWTs.
- No registration.
