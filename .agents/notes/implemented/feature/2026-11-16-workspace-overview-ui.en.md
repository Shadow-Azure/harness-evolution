# Agent Note: The workspace overview URL contract, independent blocks, and default landing

Status: implemented

English | [中文](2026-11-16-workspace-overview-ui.md)

## Problem

m8-03 exposes four read-only endpoints (summary, trend, sources, and the paged bad-case list), but the overview page still has to solve four things at once: filters must be shareable and survive a refresh; the trend and the list must not block each other (a slow or failing block must not turn the whole page into a spinner); a bad-case ID must land directly on the error detail's description tab; and `/workspaces/:wid` must move from the Session list to the overview without redirecting old Session deep links. m8-03 also only aggregates object totals and bucket totals, with no object × bucket cross-count, so the prototype's SourceMatrix has no honest data source.

## Decision

- The URL is the single source of truth for filters: `tab=cases`, `range=7|30|90|custom`, `from`/`to` (only with `range=custom`), `grain=day|week|month`, `objects` (comma-separated, de-duplicated, empty means all, multi-select is a union), `page` (written only when greater than 1), and `type` (`self|discovery`). Defaults are `range=90` and `grain=week`; invalid, out-of-range, or malformed dates fall back; on mount the page replaces a missing or non-canonical URL once, so refreshes and shares restore the same filters.
- A custom window is expressed as `from`/`to` and sends no `range`; clicking a trend bucket switches the list window to that bucket's inclusive dates (the day itself for a day bucket, Monday through Sunday for a week bucket, the whole month for a month bucket) and returns to page one.
- Filter changes use `router.replace` (no history spam) while paging uses `router.push`; adding or removing objects, removing a chip, and clearing filters all only change the URL, so components never keep a second copy of filter state.
- `type` is an extra list filter key: the prototype stat strip is not clickable, but 08 §6.2 requires the self / discovery metrics to write a list filter and scroll to the list, so those two cells are buttons that write `type` and clear it on a second click; a shortcut next to the source metric focuses the source multi-select.
- Switching workspaces resets the filters to defaults: one watcher owns both URL canonicalization and the workspace-change reset. Two separate watchers let a canonicalization navigation cancel the reset navigation in the same tick (a race observed in practice); merging them lets the reset win and skip that pass's canonicalization.
- The stat strip, the trend plus source distribution, and the list are three independent request blocks: each has its own skeleton, empty state, block-level `ErrorState`, and retry; empty copy distinguishes "this workspace has no bad cases" from "the current filters match nothing", and the latter offers a clear action.
- The trend is hand-drawn SVG: `chartGeometry.ts` only does pure geometry (1/2/5×10ⁿ ticks, `min(28, slot*0.6)` bar width, stacked heights, shares) while the DOM owns axis labels and the tooltip; a `0` value draws no bar but keeps a clickable and focusable bucket area; more than 26 buckets switch to dense mode with sparse labels.
- The bad-case ID is the only in-row link, with `target="_blank" rel="noopener"` pointing at `/workspaces/:wid/sessions/:sid/errors?case=<id>&tab=desc`; the row itself is not clickable.
- Only the bad-case tab ships: `tab=targets` canonicalizes back to `tab=cases` with an M11 notice, and the "evolution targets overview" button stays visible but `disabled` instead of hiding controls to pretend the capability is absent.
- The default landing moves to the overview: `DEFAULT_WORKSPACE_PATH` becomes `overview`, `/workspaces/:wid` redirects to `overview`, and login plus workspace choice share `defaultLandingPath`; `legacyWorkspaceTarget` still maps `/sessions` and `/errors` to the Session list and only `/` enters the overview; `switchableWorkspaceChild` keeps `/sessions` when switching workspaces. The overview route is lazy-loaded, and the top nav gains an overview entry before Sessions.
- No SourceMatrix: m8-03 has no per-object × bucket field, and stitching a matrix from the current eight-row page would produce wrong totals. The source distribution shows the top six plus a "remaining N sources" aggregate row that can expand to all.
- Contract types are re-exported from the m8-03 generated `components["schemas"]` through `packages/contracts/src/overview.ts`; this issue adds or changes no HTTP endpoint.
- The page has no write operation: filters, chart, and list are all read-only, and viewers see the same view as administrators.

## Alternatives considered

- **Stitch an object × bucket matrix from the current page's bad cases**: rejected. The list has eight rows per page, so cross-bucket counts would be systematically low and would change with paging; that is fabricated data, not a degradation.
- **Keep sessions as the default landing and only add a nav item**: rejected. The issue requires the overview to become the workspace root; preserving the old `/sessions` mapping is enough for old links.
- **Add a third-party chart library**: rejected. The trend is just stacked bars plus axes and a tooltip; hand-drawn SVG reuses the existing tokens, adds no first-screen bundle, and avoids stacking a chart theme on top of Element Plus.
- **Keep the `type` filter in component state instead of the URL**: rejected. After a refresh or share the list and chart would silently disagree; the URL as the single source is the page's most verifiable contract.
- **Use two watchers for canonicalization and workspace reset**: rejected. In the same tick the canonicalization started a navigation with the old filters and cancelled the reset, leaking the old workspace's `objects` into the new one; one merged watcher is deterministic.
- **Silently return to cases for `tab=targets`, or hide the tab**: rejected. Silent redirects look like broken links, while hiding cannot express the M11 boundary; a disabled entry plus a one-time notice is the honest option.
- **Keep the prototype's right column (quota / ingest / current workspace)**: rejected. Quota is already the sixth stat cell, and ingest plus member details belong to workspace administration; this issue neither copies admin capabilities nor introduces a second quota figure.
- **Use a whole-page spinner or load the four requests serially**: rejected. The matrix and the list differ in volume, and any single failure would take down the page; independent block requests are what "chart and list do not block each other" requires.

## Consequences

- The URL has one more key than the issue listed: `type`. Only the stat strip writes it and it disappears by default. Unknown source names in `objects` are passed to the API as-is (the server filters them out naturally), and a workspace switch resets everything, so filters never leak across workspaces.
- Old `/errors` and `/sessions` links still land on the Session list; only the application root `/` moves to the overview. External bookmarks pointing at `/workspaces/:wid` without a child path now open the overview instead of the Session list, as this issue intends.
- The SourceMatrix and the object × bucket detail remain an explicit debt: m8-03 needs an object-bucketed count (or a trend reused under an object filter), and the frontend must not assemble it.
- The deferred targets tab still lacks F25; until M11, any `tab=targets` link only sees cases plus the notice.
- Dense mode compresses labels only above 26 buckets; 60+ buckets still render every clickable area and compress horizontally rather than scroll, guarded by the 390px no-horizontal-overflow E2E assertion.
- The E2E suite creates its own workspace and ingests eleven "today/yesterday" bad cases with a credential, so assertions do not depend on the fixtures' fixed historical dates; the default-landing case only checks structure on ws-default and never asserts specific counts.
- The page has no write entry, so viewer roles need no extra button-level degradation; adding ingest or launch entry points later will require a read-only state as well.
