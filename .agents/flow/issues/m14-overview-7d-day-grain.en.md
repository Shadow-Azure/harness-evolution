# Overview 7-day trend is weekly, so 11-19 has no separate count (prototype now defaults to day grain; implementation pending)

English | [中文](m14-overview-7d-day-grain.md)

```yaml flow
kind: issue
id: m14-02
milestone: m14
depends: []
priority: P1
status: done
scope:
  - apps/web/src/pages/overview/**
  - tests/e2e/**
  - plans/**
  - .agents/notes/**
  - .agents/flow/**
adr:
  - ../../notes/implemented/feature/2026-11-19-overview-7d-day-grain.md
github:
  number: 375
  url: https://github.com/Shadow-Azure/harness-evolution/issues/375
```

## Background

On 2026-11-19 the production overview page showed four bad cases reported on 11-19 in the list, but the "bad case trend" had only two weekly buckets, `11-09` and `11-16`, and no separate 11-19 bucket. The counts agree: 33 reported at the top, 33 in the list, and 33 in the 11-16 bucket, so the data is counted in the 11-16 week and is not lost by ingest or aggregation. The issue is that a 7-day window still uses weekly grain and the chart labels only the bucket start.

The prototype has been updated first to the product expectation: selecting the last 7 days in `plans/ui-prototype-v2/harness-evolution.html` now defaults to day grain. The production implementation has not followed yet. The before/after screenshots and full evidence are on GitHub #375.

## Goals

- The last-7-days quick range defaults to day grain and returns seven daily buckets, with the current day visible.
- The last-30/90-days quick ranges default to week grain; a later manual day/week/month choice is not overwritten by data refreshes.
- `?range=7` without an explicit valid `grain` normalizes to `day`; an explicit `?range=7&grain=week` is still honored.
- The prototype, design docs, and production implementation share the same default; no API, database, or statistic-definition change.

## Design authority

- [08 §6.2 interactions and URL](../../../plans/fullstack-design/08-frontend-implementation.md#62-交互与-url): overview time/grain, URL state, and list independence.
- [05 §4.18 overview read endpoints](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2): `grain` and window semantics; the server already supports day/week/month.
- [V2 design §5.1 metrics and filters](../../../plans/ui-prototype-v2/design-v2.md#51-指标与筛选): time/grain controls and overview interactions.
- [V2 prototype overview](../../../plans/ui-prototype-v2/harness-evolution.html): updated in this change to default 7 days to day grain.
- Agent Note: [2026-11-19-overview-7d-day-grain](../../notes/implemented/feature/2026-11-19-overview-7d-day-grain.en.md).

## Implementation

- `apps/web/src/pages/overview/overviewUrl.ts`: `parseOverviewQuery` falls back to `day` for `range=7` when no explicit valid `grain` is present; an explicit grain wins.
- `apps/web/src/pages/overview/Index.vue`: `setRange` couples the quick range to a default grain—7 days → day, 30/90 days → week; a custom window keeps the current grain; re-clicking the active range is a no-op.
- `apps/web/src/pages/overview/overviewUrl.test.ts` and `Index.test.ts`: cover 7-day default day, explicit week preservation, 30/90 default week, and manual grain not being overwritten before a range change.
- `tests/e2e/m8-04-overview.test.mjs`: covers clicking the 7-day range, the `grain=day` URL, seven daily buckets, the current-day bucket, and 30/90 returning to week grain.
- `plans/fullstack-design/08-frontend-implementation.md`: records the range/grain coupling.
- No changes to `apps/api`, `packages/contracts`, database migrations, or statistic queries.

## Implementation steps

1. Change URL parsing and the page `setRange` default-grain coupling.
2. Add unit/component tests for defaults, explicit overrides, and quick-range changes.
3. Add E2E coverage for seven daily buckets, the current-day bucket, and 30/90 week grain.
4. Update the design doc and Agent Note; run typecheck/lint/unit tests/focused E2E.
5. Open a PR with before/after screenshots and smoke evidence; handle CI and review.

## Dependencies and boundary

- No new dependency; the backend trend already supports day grain, so this issue changes only frontend defaults and URL normalization.
- Boundary: only overview time/grain coupling, its tests, and design docs; no chart geometry, list filters, API fields, data structures, or permissions.
- An explicit `grain=week` link for a 7-day window must stay weekly; the 30/90-day weekly default must not regress.

## Verification

```sh
pnpm test:web -- --run src/pages/overview/overviewUrl.test.ts src/pages/overview/Index.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- --pattern m8-04-overview
pnpm verify:flow --diff origin/main
```

- Expected: unit tests cover the 7-day day default and explicit grain; E2E sees seven `[data-bucket]` nodes, the current-day bucket, and the "按日聚合" hint for 7 days, and "按周聚合" for 30/90 days; typecheck/lint/CI pass.

## Acceptance

- Clicking "last 7 days" yields `range=7&grain=day`, seven daily buckets, and a visible current-day bucket with the correct count.
- Opening `?range=7` normalizes to day; explicit `?range=7&grain=week` still shows weekly buckets.
- Clicking "last 30 days" / "last 90 days" defaults to week; a manual month choice is not overwritten until the next range change.
- The existing 30/90-day 14 weekly buckets, list filters, and statistics do not regress.
- The prototype and implementation share the default; the PR contains before/after screenshots.

## Gates and CI

- `verify:flow --diff origin/main` covers this issue reference and scope.
- `web-static` (lint/typecheck/style), `unit-tests`, `e2e`, and `docs-flow` pass.
- The PR title contains `(#375)` and its description has prototype before/after screenshots and smoke results.

## Non-goals

- No new "new today" metric, no trend-chart redesign, no chart geometry or color change.
- No bad-case ingest, sync, timezone, statistic-definition, or API-contract change.
- No change to explicit `grain` semantics and no day default for long windows.
