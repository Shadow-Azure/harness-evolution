# Agent Note: 7-day overview defaults to day grain

Status: implemented

English | [中文](2026-11-19-overview-7d-day-grain.md)

## Problem

The workspace overview's "bad case trend" defaults to a 90-day window with weekly grain. When a person switches to the last 7 days, `range` becomes 7 but `grain` stays `week`, so the 7-day window only produces two weekly buckets (for example 11-09 and 11-16). The current day (11-19) is folded into the 11-16 bucket, there is no 11-19 bucket, and the missing bar is easily mistaken for unreported data or a broken statistic.

In `plans/ui-prototype-v2/harness-evolution.html`, "time" and "grain" are also independent controls and the prototype did not switch to day grain for a 7-day range either. Product confirmed that the 7-day view should show per-day data, so the prototype was updated first and the production implementation now follows it.

## Decision

- Quick ranges own a default grain: last 7 days → `day`, last 30/90 days → `week`; custom windows keep the current grain. The coupling happens only when the range actually changes; re-clicking the active range is a no-op; a later manual day/week/month choice is not overwritten by data refreshes.
- URL parsing: `?range=7` without an explicit valid `grain` normalizes to `day`; an explicit `?range=7&grain=week` is still honored. `overviewQuery` therefore writes `grain=day` into the canonical URL.
- No API, database, or statistic-definition change: the backend already supports day/week/month, and a day request over 92 days keeps the existing server-side downgrade to week with the effective grain returned.
- Prototype sync: the click path and `?range=7` boot path in `plans/ui-prototype-v2/harness-evolution.html` also default to day; `design-v2.md` and `plans/fullstack-design/08` record the convention.

## Alternatives considered

- **Keep weekly grain for 7 days and only add a tooltip with the week range**: rejected. It explains the number but leaves the main "last 7 days" path without per-day detail; two buckets cannot support daily triage.
- **Add a "new today" count to the stat strip**: rejected. It adds one number but does not restore the daily trend, and it introduces another metric definition.
- **Default every range to day grain**: rejected. A 90-day day request would be downgraded to week server-side and the client would still need the downgrade notice; weekly is the existing default for long windows.

## Consequences

- A 7-day URL canonicalizes from `?range=7` to `?range=7&grain=day`, and the chart changes from two weekly buckets to seven daily buckets; explicit `grain=week` links keep their weekly view.
- The 30/90 quick buttons reset the grain to week; a person who manually picked month and then clicks 30/90 sees that one change, which is the intended range-change coupling.
- A custom window keeps the grain it was entered with and does not infer a grain from the span: entering a 7-day custom window from 90 days/week still shows weekly buckets, so switch to day manually for the daily view.
- Tests cover URL parsing, page range/grain coupling, and the seven visible daily buckets in E2E; the prototype and the implementation share the same default.
