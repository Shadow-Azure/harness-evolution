# Seven-step run detail and execution events

English | [中文](m10-06-seven-step-run-detail.md)

```yaml flow
kind: issue
id: m10-06
milestone: m10
depends:
  - m10-04
  - m10-05
priority: P1
status: backlog
scope:
  - apps/web/src/pages/evolution/**
  - apps/web/src/composables/**
  - apps/web/src/api/**
  - tests/e2e/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 215
  url: https://github.com/Shadow-Azure/harness-evolution/issues/215
```

## Background

Run detail must explain sessions, potential, attribution, clusters, and blockers.

## Goals

- Render server steps.
- Show cache and non-target states.
- Link logs to steps and clusters.

## Design authority

- [08 §10](../../../plans/fullstack-design/08-frontend-implementation.md)：运行详情。
- [05 §3.6](../../../plans/fullstack-design/05-api-design.md)：七步响应外壳。

## Implementation

- Page steps two through four.
- Rank clusters by severity.
- Expose attribution retry.

## Implementation steps

1. Write step tests.
2. Build components.
3. Add log E2E.

## Dependencies and boundary

- Dependencies: m10-04, m10-05
- Boundary: no event storage changes.

## Verification

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern run-detail-v2
```

- Legacy and new runs use seven steps.
- Unready steps are not requested.
- Non-target stays out of clusters.

## Acceptance

- The UI consumes run.steps only.
- SSE and REST agree.

## Gates and CI

- Web, E2E, bundle, and flow gates.

## Non-goals

- No second step schema.
- No free-text error exposure.
