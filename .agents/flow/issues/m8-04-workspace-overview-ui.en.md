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
status: in-progress
scope:
  - apps/web/src/pages/overview/**
  - apps/web/src/api/**
  - apps/web/src/components/layout/**
  - apps/web/src/router/**
  - apps/web/src/router.test.ts
  - apps/web/src/ui-prototype.test.ts
  - apps/web/src/composables/**
  - packages/contracts/src/**
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
- The URL is the single source of truth for filters: `tab=cases`, `range=7|30|90|custom`, `from`/`to` (custom window only), `grain=day|week|month`, `objects` (comma-separated, empty means all, multi-select is a union, chips remove one), `page`, and `type` (stat-cell drill-down into self / discovery). Defaults are `range=90` and `grain=week`; invalid or missing values fall back; switching workspaces resets the filters.
- The stat strip, trend with source distribution, and bad-case list fetch and render independently with block-level retry; there is no whole-page spinner. Clicking a bucket switches the list window to that bucket's inclusive dates; a bad-case ID opens `/workspaces/:wid/sessions/:sid/errors?case=<id>&tab=desc` in a new window.
- The overview becomes the workspace default landing page (`/workspaces/:wid` redirects to `/overview`, and login plus workspace-choice landing share the same target); the top nav gains `总览` before Sessions; Session deep links keep their paths.
- `tab=targets` redirects to `tab=cases` with a notice: the targets overview (F25) waits for M11, and the disabled entry stays visible instead of shipping a dead control.
- Known gap: m8-03 exposes no per-object × bucket counters, so this issue does not fake a SourceMatrix; the source distribution shows the top six plus a folded remainder. The matrix needs a future API field instead of page-data stitching.
- Contract types are re-exported from the m8-03 generated payload through `packages/contracts/src/overview.ts`; no HTTP endpoint was added or changed.

## Implementation steps

1. Write filter tests.
2. Build the page.
3. Add E2E states.

## Dependencies and boundary

- Dependencies: m7-08, m8-03
- Boundary: F25 waits for M11.
- Boundary: the SourceMatrix (object × bucket detail) follows the m8-03 aggregation contract and is deferred with it; this issue does not build it.

## Verification

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern "m8-04 overview"; pnpm test:e2e -- --pattern "m1-shell|m7-08 workspace-shell"
```

- Filters survive reload and match request parameters.
- An empty objects selection means all; the union and chip removal behave.
- The drill-down URL selects the right case's description tab.
- 390px has no horizontal overflow and the console stays clean.

## Acceptance

- Prototype IA is met.
- Sections load independently.

## Gates and CI

- Web, E2E, bundle, and flow gates.

## Non-goals

- No chart dependency.
- No cross-workspace aggregate.
