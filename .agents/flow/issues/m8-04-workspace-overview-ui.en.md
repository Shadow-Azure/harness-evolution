# Workspace overview page and error-detail drill-down

English | [中文](m8-04-workspace-overview-ui.md)

```yaml flow
kind: issue
id: m8-04
milestone: m8
depends:
  - m7-08
  - m8-03
priority: P1
status: backlog
scope:
  - apps/web/src/pages/overview/**
  - apps/web/src/api/**
  - apps/web/src/components/**
  - tests/e2e/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 234
  url: https://github.com/Shadow-Azure/harness-evolution/issues/234
```

## Background

Users need one workspace view for sources, trends, and drill-down.

## Goals

- Build stats, filters, chart, and list.
- Persist filters in the URL.
- Deep-link cases to problem detail.

## Design authority

- [08 §6](../../../plans/fullstack-design/08-frontend-implementation.md)：总览页面结构。
- [design-v2.md §5](../../../plans/ui-prototype-v2/design-v2.md)：总览原型。

## Implementation

- Use SVG and existing tokens.
- Expose bucket downgrade.
- Handle empty and error states.

## Implementation steps

1. Write filter tests.
2. Build the page.
3. Add E2E states.

## Dependencies and boundary

- Dependencies: m7-08, m8-03
- Boundary: F25 waits for M11.

## Verification

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern overview
```

- Filters restore.
- Empty selection means all.
- Drill-down selects the case.

## Acceptance

- Prototype IA is met.
- Sections load independently.

## Gates and CI

- Web, E2E, bundle, and flow gates.

## Non-goals

- No chart dependency.
- No cross-workspace aggregate.
