# Evolution-target overview UI

English | [中文](m11-04-target-overview-ui.md)

```yaml flow
kind: issue
id: m11-04
milestone: m11
depends:
  - m8-04
  - m11-03
priority: P1
status: in-progress
scope:
  - apps/web/src/pages/overview/**
  - apps/web/src/components/**
  - apps/web/src/api/**
  - apps/web/src/composables/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 219
  url: https://github.com/Shadow-Azure/harness-evolution/issues/219
```

## Background

The prototype provides a second object-centric overview tab.

## Goals

- Add dual overview tabs.
- Filter trends by target and state.
- Keep target detail filters independent.

## Design authority

- [08 §6.1–§6.3](../../../plans/fullstack-design/08-frontend-implementation.md)：对象总览组件。
- [design-v2.md §5.3](../../../plans/ui-prototype-v2/design-v2.md)：对象视角原型。

## Implementation

- Share window context.
- Page sidebar targets.
- Explain all distributions.

## Implementation steps

1. Write tab tests.
2. Implement charts and lists.
3. Add knowledge labels and E2E.

## Dependencies and boundary

- Dependencies: m8-04, m11-03
- Boundary: P1 extension.

## Verification

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern target-overview
```

- Tabs preserve shared time.
- Target filters are independent.
- Empty targets link to setup.

## Acceptance

- The prototype view is met.
- Numbers share one source.

## Gates and CI

- Web, E2E, bundle, and flow gates.

## Non-goals

- No chart dependency.
- No automatic setup beyond the request.
