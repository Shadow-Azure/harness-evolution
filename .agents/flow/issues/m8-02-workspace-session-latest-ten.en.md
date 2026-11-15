# Workspace session projection, latest ten, and Enter search

English | [中文](m8-02-workspace-session-latest-ten.md)

```yaml flow
kind: issue
id: m8-02
milestone: m8
depends:
  - m7-06
  - m8-01
priority: P0
status: in-progress
scope:
  - apps/api/app/api/sessions.py
  - apps/api/app/service/sessions/**
  - apps/api/app/db/crud/sessions.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 232
  url: https://github.com/Shadow-Azure/harness-evolution/issues/232
```

## Background

The workspace session page should initially load only ten sessions and support exact root-ID search.

## Goals

- Return limit ten, total, and pending counts.
- Search by root session ID.
- Expose explicit empty-state data.

## Design authority

- [05 §3.10、§4.18](../../../plans/fullstack-design/05-api-design.md)：空间 Session DTO。
- [08 §5.2.1](../../../plans/fullstack-design/08-frontend-implementation.md)：最新 10 条交互。

## Implementation

- Project sessions through workspace bad cases.
- Use stable ordering.
- Distinguish totals from pending sync.

## Implementation steps

1. Write default/search tests.
2. Implement projection.
3. Verify indexes.

## Dependencies and boundary

- Dependencies: m7-06, m8-01
- Boundary: no frontend layout.

## Verification

```sh
pnpm test:api -- tests/sessions; pnpm contract:check
```

- Default size is ten.
- Root ID search is exact.
- Cross-workspace search cannot leak.

## Acceptance

- The API supports the latest-ten contract.
- Pending sessions are counted.

## Gates and CI

- API, database, contract, and flow gates.

## Non-goals

- No full-list default.
- No message-body search.
