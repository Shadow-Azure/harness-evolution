# Workspace-scope targets, runs, events, and SSE

English | [中文](m7-07-evolution-resource-workspace-scope.md)

```yaml flow
kind: issue
id: m7-07
milestone: m7
depends:
  - m7-03
  - m7-05
priority: P0
status: in-progress
scope:
  - apps/api/app/api/evolution_*.py
  - apps/api/app/api/events.py
  - apps/api/app/service/evolution/**
  - apps/api/app/service/events.py
  - apps/api/app/db/crud/**
  - apps/api/app/db/models/**
  - apps/api/app/api/catalogs.py
  - apps/api/app/api/deps.py
  - apps/api/app/main.py
  - apps/api/app/service/catalogs.py
  - apps/api/app/service/identity/schemas.py
  - apps/api/app/service/workspaces/service.py
  - apps/api/tests/**
  - packages/contracts/**
  - plans/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 228
  url: https://github.com/Shadow-Azure/harness-evolution/issues/228
```

## Background

Targets, runs, events, and SSE tickets are workspace resources.

## Goals

- Scope evolution resources by workspace.
- Allow space admins to configure and launch.
- Bind tickets to workspace membership.

## Design authority

- [01 §4.3、§4.4](../../../plans/fullstack-design/01-architecture.md)：运行与鉴权链路。
- [05 §4.20](../../../plans/fullstack-design/05-api-design.md)：V2 运行端点。

## Implementation

- Change the target uniqueness key.
- Filter run and event APIs.
- Add workspaceId to tickets.
- The routing, ticket-field, catalog, and visible-space filtering work also extends assembly (`main`, `deps`), catalogs, identity contracts, and workspace service scope; those edits only serve this issue's space boundary and do not change their existing responsibilities.
- Produce the structured PR review document in `plans/` according to `docs/review.md`.

## Implementation steps

1. Write isolation tests.
2. Migrate services and routes.
3. Update compatibility contracts.

## Dependencies and boundary

- Dependencies: m7-03, m7-05
- Boundary: no state-machine reorder.

## Verification

```sh
pnpm test:api -- tests/evolution tests/events; pnpm contract:check
```

- Cross-workspace access fails.
- Object names are unique per workspace.
- Wrong-workspace tickets fail.

## Acceptance

- Space admins can operate their workspace.
- Viewers cannot write.

## Gates and CI

- API, event, contract, and flow gates.

## Non-goals

- No PotentialMatcher.
- No iteration or evaluation state-machine changes.
