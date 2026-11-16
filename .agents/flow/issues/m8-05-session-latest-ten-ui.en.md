# Session latest-ten UI and Enter search

English | [中文](m8-05-session-latest-ten-ui.md)

```yaml flow
kind: issue
id: m8-05
milestone: m8
depends:
  - m7-08
  - m8-02
priority: P1
status: in-progress
scope:
  - apps/web/src/pages/sessions/**
  - apps/web/src/api/**
  - tests/e2e/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
adr: []
github:
  number: 235
  url: https://github.com/Shadow-Azure/harness-evolution/issues/235
```

## Background

The session page should switch from broad reactive filtering to latest-ten plus explicit search.

## Goals

- Request ten initially.
- Search on Enter.
- Restore ten when cleared.

## Design authority

- [08 §5.2.1](../../../plans/fullstack-design/08-frontend-implementation.md)：最新 10 条与空态。
- [05 §4.18](../../../plans/fullstack-design/05-api-design.md)：q 与 limit。

## Implementation

- Submit search explicitly.
- Show totals and pending count.
- Clear stale detail on miss.

## Implementation steps

1. Write request tests.
2. Change query flow.
3. Add E2E coverage.

## Dependencies and boundary

- Dependencies: m7-08, m8-02
- Boundary: no error-detail changes.

## Verification

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern session-latest-ten
```

- Typing does not request.
- Enter requests once.
- Misses clear detail.

## Acceptance

- At most ten load initially.
- Search states match the prototype.

## Gates and CI

- Web, E2E, and flow gates.

## Non-goals

- No live fuzzy search.
- No full initial list.
