# Collapsible multi-attribution error-detail sidebar

English | [中文](m11-02-multi-attribution-error-detail.md)

```yaml flow
kind: issue
id: m11-02
milestone: m11
depends:
  - m7-08
  - m10-05
  - m11-01
priority: P0
status: done
scope:
  - apps/web/src/pages/errors/**
  - apps/web/src/components/**
  - apps/web/src/api/**
  - apps/web/src/composables/**
  - apps/web/src/router/**
  - apps/web/src/utils/**
  - apps/web/src/test/**
  - packages/contracts/**
  - plans/**
  - tests/e2e/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 217
  url: https://github.com/Shadow-Azure/harness-evolution/issues/217
```

## Background

One case can now have multiple revision-scoped attributions.

## Goals

- Group cases with collapsible attribution lists.
- Page two items per group.
- Restore case and item deep links.

## Design authority

- [08 §7](../../../plans/fullstack-design/08-frontend-implementation.md)：多归因错误详情。
- [design-v2.md §8](../../../plans/ui-prototype-v2/design-v2.md)：原型交互。

## Implementation

- Add group and item components.
- Use case, tab, and at URL state.
- Offer launch from empty attribution.

## Implementation steps

1. Write interaction tests.
2. Rebuild the sidebar.
3. Add E2E.

## Dependencies and boundary

- Dependencies: m7-08, m10-05, m11-01
- Boundary: execution-flow DAG/structure-tree layout is owned by m11-07; this issue does not change it.
- This issue consumes the m11-01 attribution contracts and `at` deep links, so its scope includes `apps/web/src/{router,utils,composables,test}/**`, `packages/contracts/**`, and `plans/**` for the review record.

## Verification

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern multi-attribution
```

- Groups expand.
- Refresh restores selection.
- Unauthorized users see no launch.

## Acceptance

- Non-target and unanalyzed remain distinct.
- Workspace switches clear detail.

## Gates and CI

- Web, E2E, bundle, and flow gates.

## Non-goals

- No manual attribution.
- No row-only navigation.
