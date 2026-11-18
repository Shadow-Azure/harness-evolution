# Agent Note: Overview bad-case list filters

Status: implemented

English | [中文](2026-11-18-bad-case-list-filters.md)

## Problem

The workspace overview puts time range, grain, and report source in the page header, where they serve the trend chart, source distribution, and stat strip. The bad-case list borrows the same parameters, so a user cannot narrow the list while keeping the chart context. The V2 prototype offers independent start date, end date, report source, and problem type controls in the list header, and an empty date means no time restriction; production has neither.

The hard part is not the four controls but "empty means unrestricted": the existing `GET /workspaces/{wid}/bad-cases` resolves a request without date parameters to the last 90 days and rejects anything wider than 366 days. Translating an empty date into any existing window would make the list look unrestricted while silently hiding older rows.

## Decision

- `overviewUrl.ts` adds `listFrom`, `listTo`, and `listObject` to the list (URL keys `lfrom`, `lto`, `lobject`), and keeps the existing `page` and `type` as the list page and type. Old URLs keep their `page`/`type` meaning.
- The list query reads only those list fields: a complete date pair sends `from/to`, otherwise `allTime=true`; source sends `objects=<one>`; type sends `badCaseType`. Trend and stats keep reading `range`, `objects`, and `grain`.
- The list endpoint gains an optional boolean `allTime`. When true, window resolution and the date predicates are skipped while source, type, and paging still apply. This is the slice's only contract extension: no new endpoint, table, or client-side full-data filtering.
- Chart-level filters, clearing, and tab switches no longer reset the list page; any list filter change resets `page` to 1. Clicking a trend bucket writes only `lfrom/lto` and never rewrites the chart window.
- The start/end inputs keep a local draft: only a complete, ordered pair is written to the URL; a single boundary or an inverted pair keeps the previous valid result, shows an inline explanation, and issues no request. Clearing both immediately restores `allTime`.
- The list header keeps the type chip (clears only the type) and a whole-list reset. A filter miss uses the "当前筛选没有命中" empty state with a clear action, while a workspace with no data keeps the workspace-level empty state.

## Alternatives considered

- **Map an empty date to `range=90` or a 366-day window**: smallest change, but "empty means unrestricted" would be false and bad cases older than a year would disappear; rejected.
- **Fetch everything in the browser and filter locally**: breaks the existing server-side paging and total contract and degrades as the list grows; rejected.
- **Add `range=all`**: makes window resolution, grain, and the 422 contract understand a special value that affects three other read endpoints; rejected in favor of a list-only boolean.
- **Rename every list field to `list*`**: `type`/`page` already affect only the list, so renaming would force a URL migration for no behavior gain; the old keys stay and only the genuinely new date/source keys are added.
- **Let the global "clear filters" clear the list too**: the two layers are independent now, and a combined clear would discard context the user just set; each layer clears itself.

## Consequences

- The list shows every report in the workspace by default. A huge workspace still reads one `pageSize=8` page per request; the `count(*)` uses the `workspace_id` index and is acceptable.
- When `allTime` appears together with `from/to/range`, it wins; the API document states this. The other overview endpoints ignore the parameter.
- Old URLs still parse, but their `objects` now affect only the chart and no longer narrow the list; that behavior change is intentional for this slice.
- The list reuses the `page`/`type` URL keys shared with the evolution-target view; the existing tab-switch logic still resets them.
- Multi-source or one-sided-open date filters would need a new contract discussion and must not reuse this parameter.
