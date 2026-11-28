# Keep the overview bad-case list in place across pagination

English | [中文](bugfix-overview-bad-case-paging-scroll.md)

```yaml flow
kind: issue
id: bugfix-78
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - apps/web/src/pages/overview/**
  - apps/web/src/composables/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-28-overview-bad-case-paging-scroll.md
github:
  number: 670
  url: https://github.com/Shadow-Azure/harness-evolution/issues/670
```

## Background

A user reports that on the overview page's bad-case list, clicking "Next" the first time a page is visited produces a refresh-like flash and jumps to the top of the page; returning to an already-visited page does not jump. The problem appears only when the page is uncached, which points at the pagination loading state rather than routing or a full document reload.

`BadCaseTable.vue` currently replaces the whole table and pager with four skeleton rows while `loading`; `useOverviewCases` pages by `page`, so an unvisited page has no cache and must pass through that loading state. Removing the rows and pager at once collapses the overview scroll container's content, the browser clamps `scrollTop` to the new maximum, and the view appears to jump to the top. A visited page has cached data ready synchronously, never shrinks like this, and therefore does not reproduce the jump.

## Goals

- Keep the list reading position for both first visits and revisits, with no full-page refresh or scroll jump.
- Keep the previous valid rows and the pager visible while loading, so the list area stays stable and the pager stays locatable.
- Keep page number, filters, and data consistent; allow retrying failures; prevent an older request from overwriting a newer page.
- Add browser regressions for the first request, the cache-hit path, and failure retry, and run them in CI.

## Design authority

- [08 §6 Workspace overview](../../../plans/fullstack-design/08-frontend-implementation.md#6-工作空间总览页pagesoverviewindexvuev2): a list filter change resets `page=1` and keeps the previous valid result until the new query returns; list paging only changes the list page number.
- [V2 prototype overview list](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html): the bad-case list and pager render as stable blocks of one card instead of rebuilding the page on paging.

## Implementation

- Query layer: `useOverviewCases` keeps the previous valid result through `placeholderData` until the new query returns, but never falls back to data from another workspace.
- Component layer: `BadCaseTable` shows the skeleton only on the first load with no data. When data exists, paging or filter changes keep rendering the old rows, add `aria-busy` and a loading hint, and leave the pager visible and operable.
- Data layer: paging stays driven by the URL `page`; query keys are per page, so an older response writes only its own cache key and cannot overwrite a newer page.
- Tests: component tests cover the first-load-only skeleton and retained rows plus pager during loading; a page-level test covers placeholder data across paging; a browser test uses three synthetic pages, delayed responses, and injected failures to cover the first request, cache hit, and failure retry, asserting no scroll jump and no document reload.
- Docs: update `08 §6.2` with the implemented list loading behavior and record the root cause and trade-offs in an Agent Note.

## Implementation steps

1. Prepare at least three synthetic bad-case pages, scroll to the list bottom, visit pages 2 and 3 for the first time, and observe scroll position, list height, and loading state.
2. Keep the previous valid result and pager during the list loading state, then record scroll positions on the first-request and cache-hit paths.
3. Add component, page-level, and browser regressions covering a short last page, failure retry, and rapid paging.
4. Run the focused E2E, frontend unit tests, types and lint, docs and flow gates, and update the design doc and Agent Note.

## Dependencies and boundary

- No blocking dependency; scope is the overview bad-case list loading and paging behavior plus its regressions. No API, contract, data semantics, page size, or ordering change.
- Do not redesign the overview, change the existing separation between global filters and list filters, or change the workspace shell's scroll ownership.

## Verification

```sh
pnpm test:e2e -- --pattern overview
pnpm --filter @harness/web test
pnpm typecheck:web
pnpm lint:web
pnpm verify:flow
```

- With at least three synthetic pages at a 1500×837 viewport, clicking "Next" at the list bottom keeps `scrollTop` above 0 before, during, and after the request, never jumps to the top, and produces no document reload.
- Returning to a visited page and paging again shows cached rows immediately and keeps the scroll position.
- A short last page, a failed request followed by retry, and rapid paging all end with the correct page number and data.
- The focused E2E, frontend unit tests, types, lint, and flow gates pass.

## Acceptance

- Unvisited and visited pages never trigger a full-page refresh or a scroll jump to the top.
- The list area stays stable while loading; the previous valid rows and pager stay visible.
- Page number, filters, and data correspond; failures can be retried and an older request never overwrites a newer page.
- Browser regressions cover the first request, cache hit, and failure retry, and run in CI.

## Gates and CI

- Run the focused browser regression, frontend unit tests (coverage at least 80%), types and lint, plus `verify:docs` and `verify:flow`.
- The new E2E runs in the existing e2e lane; no separate workflow is added.

## Non-goals

- Do not redesign the overview or change ordering, page size, statistics, or server caching.
- Do not modify the API or contracts, or add pagination or scrolling libraries.
- Do not hide the pager or remove the skeleton's first-load purpose to mask the symptom.
