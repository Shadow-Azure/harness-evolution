# Workspace bad-case overview aggregation API

English | [中文](m8-03-workspace-overview-api.md)

```yaml flow
kind: issue
id: m8-03
milestone: m8
depends:
  - m8-02
priority: P0
status: in-progress
scope:
  - apps/api/app/api/overview.py
  - apps/api/app/service/overview/**
  - apps/api/app/db/crud/**
  - apps/api/app/main.py
  - apps/api/app/errors.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 233
  url: https://github.com/Shadow-Azure/harness-evolution/issues/233
```

## Background

The overview aggregates object and time dimensions and supports an unfiltered paged list.

## Goals

- Provide summary, trend, sources, and list APIs.
- Treat empty selection as all objects.
- Fill empty buckets.

## Design authority

- [05 §3.10、§4.18](../../../plans/fullstack-design/05-api-design.md)：总览 DTO 与端点。
- [06 §7.5](../../../plans/fullstack-design/06-database-design.md)：时间与空间口径。

## Implementation

- Filter every query by workspace.
- Return overview totals.
- Add composable list filters.

## Implementation steps

1. Write SQL and bucket tests.
2. Implement aggregation.
3. Add validation errors.

## Dependencies and boundary

- Dependencies: m8-02
- Boundary: no chart or target view.

## Verification

```sh
pnpm test:api -- tests/overview; pnpm test:db:mysql
```

- Selection uses a union.
- Buckets are continuous.
- Filters may all be empty.

## Acceptance

- Counts match SQL.
- No cross-workspace rows leak.

## Gates and CI

- API, MySQL, contract, and flow gates.

## Non-goals

- No chart rendering.
- No target overview.
