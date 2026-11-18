# Add list-level bad case filters

English | [中文](m12-09-bad-case-list-filters.md)

```yaml flow
kind: issue
id: m12-09
milestone: m12
depends:
  - m8-04
  - m12-07
priority: P1
status: in-progress
scope:
  - apps/web/src/pages/overview/**
  - apps/web/src/api/**
  - apps/api/app/api/overview.py
  - apps/api/app/service/overview/**
  - apps/api/app/db/crud/overview.py
  - apps/api/tests/m8-03-workspace-overview/**
  - apps/api/tests/test_openapi.py
  - packages/contracts/**
  - tests/e2e/m8-04-overview.test.mjs
  - tests/e2e/m12-08-overview-actions-context.test.mjs
  - tests/e2e/m12-09-bad-case-list-filters.test.mjs
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 336
  url: https://github.com/Shadow-Azure/harness-evolution/issues/336
```

## Background

The production-versus-prototype bad-case list comparison shows four list-local controls in the prototype: start date, end date, report source, and problem type. Production shows only the title, total count, and pagination.

The page-level time range, grain, and source controls drive the trend chart and cannot replace the prototype's independent list filters. Users cannot narrow a list query while preserving the chart context.

This gap is independent of production data volume: production had 9 rows during capture and still had no list-local controls, while the prototype filters its 26-row sample independently.

## Goals

- Add start date, end date, report source, and problem type controls to the bad-case list header.
- Keep list filters independent from global trend time/source filters; empty values impose no restriction.
- Reset list pagination to page 1 on any filter change and expose recoverable filtered and empty states.
- Persist list filters in the URL so refresh, back navigation, and sharing preserve them.
- Reuse the existing overview bad-case endpoint and add only the minimum contract fields if necessary.

## Evidence screenshots

| Production | V2 prototype |
| --- | --- |
| [![Production bad-case list](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-01b-overview-list.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-01b-overview-list.jpeg) | [![V2 prototype bad-case list](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-01b-overview-list.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-01b-overview-list.jpeg) |

Both images are real browser-window captures at `2816×1576`. The prototype exposes date, source, and type controls in the list header; production shows only the title, total, and pagination.

## Design authority

- [08 §6.1 Overview structure](../../../plans/fullstack-design/08-frontend-implementation.md#61-结构): boundaries between stats, chart, and list.
- [08 §6.2 Interaction and URL](../../../plans/fullstack-design/08-frontend-implementation.md#62-交互与-url): persistent filter state.
- [05 §4.18 Overview and workspace Session lists](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2): bad-case pagination and query parameters.
- [05 §7 Pagination, sorting, and filtering](../../../plans/fullstack-design/05-api-design.md#7-分页排序与过滤约定): empty filters, unions, and paging.
- [V2 design §5.1 Metrics and filters](../../../plans/ui-prototype-v2/design-v2.md#51-指标与筛选): list filters are independent from chart filters.

## Implementation

- Add date range, source, and type controls to `BadCaseTable`; reuse overview source options rather than creating another enum.
- Add list-specific URL state such as `listFrom`, `listTo`, `listObject`, `listType`, and `listPage`; final names must preserve existing URL compatibility.
- Use an independent `queryKey` and query for the list; trend changes must not silently reset list state, while global filters continue to govern stats and the chart.
- An empty list date must mean truly unrestricted time. The existing list endpoint defaults to 90 days, so add the optional `allTime=true` (server skips the date predicates); this is the issue's only minimal contract extension and adds no endpoint or table.
- Do not request an invalid date range; retain the previous valid result and show an actionable local error. Clearing restores the unrestricted query.
- Distinguish filtered no-match from an empty workspace and provide a clear-filter action only for the former.
- Reset `listPage=1` on filter changes; pagination changes only `listPage`. Back/forward must restore the full list state.
- Cover filter changes, URL restoration, page reset, invalid dates, and empty states in unit tests; cover refresh and back navigation in E2E.

## Implementation steps

1. Add failing tests for list URL state, pagination reset, and empty states.
2. Extend overview URL parsing/serialization while preserving old URLs.
3. Separate list query state from global trend filters and reuse existing overview API parameters.
4. Add the four controls and a clear action to `BadCaseTable` with keyboard and aria labels.
5. Add SQLite/HTTP and E2E coverage for hits, no matches, and refresh restoration.
6. Update frontend docs and an Agent Note, then run type, web, E2E, and documentation gates.

## Dependencies and boundary

- Dependencies: m8-04 supplies the overview list and m12-07 supplies trace state; both are done.
- Boundary: add only list filters and URL state. Do not change trend semantics or create another global filter.
- The trigger-point column and API fields belong to m12-10 and must not be mixed into this issue.
- Do not perform client-side filtering over all rows; filtering and pagination remain server-side.

## Verification

```sh
pnpm test:web -- apps/web/src/pages/overview
pnpm test:api -- tests/m8-03-workspace-overview
pnpm test:e2e -- --pattern m12-09
pnpm typecheck:web
pnpm verify:flow
```

- Each filter works alone and in combination and matches API results.
- Every filter change returns to page 1; paging preserves filters.
- Refresh, browser back, and copied URLs restore list filters.
- Invalid dates, no matches, and an empty workspace produce three distinct states.
- Trends and statistics are unaffected by list filters.

## Acceptance

- The list header provides start/end date, source, and type controls.
- List filters are independent from page-global filters and empty values are unrestricted.
- URL refresh and navigation restore filters and pagination with old URL compatibility.
- Server-side totals and paginated rows agree without client-side full-data filtering.
- Empty and error states are recoverable and accessible by keyboard and screen readers.
- New tests and docs pass CI with no regression to overview, trace state, or drill-down.

## Gates and CI

- `pnpm test:web`, `pnpm test:api`, `pnpm test:e2e`, `pnpm typecheck:web`, `pnpm verify:flow`, and `pnpm lint:docs`.
- CI must cover filter-plus-pagination, old URL compatibility, and no-match branches.

## Non-goals

- Do not alter trend or stat calculations.
- Do not add client-side full-data filtering or a new table.
- Do not replace "trigger time" with "trigger point" here; m12-10 owns that semantic change.
- Do not redesign the list or pagination component.
