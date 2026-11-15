# Evolution-target overview aggregation API

English | [中文](m11-03-target-overview-api.md)

```yaml flow
kind: issue
id: m11-03
milestone: m11
depends:
  - m10-02
  - m10-03
priority: P1
status: backlog
scope:
  - apps/api/app/api/overview.py
  - apps/api/app/service/overview/**
  - apps/api/app/db/crud/**
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 218
  url: https://github.com/Shadow-Azure/harness-evolution/issues/218
```

## Background

The prototype includes object-centric overview data as a P1 extension.

## Goals

- Return target lists, trends, cases, and detail.
- Reuse matcher counts.
- Support revision and knowledge objects.

## Design authority

- [05 §3.10、§4.18](../../../plans/fullstack-design/05-api-design.md)：对象总览 DTO。
- [08 §6.1](../../../plans/fullstack-design/08-frontend-implementation.md)：对象视角结构。

## Implementation

- Deduplicate three attribution states.
- Use separate bucket times.
- Sort by evolvable count.

## Implementation steps

1. Write dedup tests.
2. Implement aggregation.
3. Test knowledge targets.

## Dependencies and boundary

- Dependencies: m10-02, m10-03
- Boundary: P1 extension.

## Verification

```sh
pnpm test:api -- tests/overview; pnpm contract:check
```

- State totals equal potential.
- Revisions deduplicate.
- Counts match the wizard.

## Acceptance

- Reads stay workspace-scoped.
- Knowledge shares the same ordering.

## Gates and CI

- API, contract, performance, and flow gates.

## Non-goals

- No cross-workspace ranking.
- No manual state edits.
