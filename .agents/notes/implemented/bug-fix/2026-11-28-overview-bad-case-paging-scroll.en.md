# Agent Note: Keep the overview bad-case list scroll position across pagination

Status: implemented

English | [中文](2026-11-28-overview-bad-case-paging-scroll.md)

## Problem

On the overview page, clicking "Next" in the bad-case list made the first visit to an unvisited page feel like a refresh and jump to the top; returning to an already-visited page behaved normally ([GitHub #670](https://github.com/Shadow-Azure/harness-evolution/issues/670)). The reporter gave no on-site measurements, so the behavior is reproduced with synthetic data.

`BadCaseTable.vue` replaces the whole table and pager with four skeleton rows while `loading`; `useOverviewCases` keys each page by `page`, so an unvisited page has no cache and always crosses that loading state. With 20 synthetic cases (8 per page, 3 pages) at a 1500×837 viewport and the list scrolled to the bottom: before clicking next, `scrollTop` is 461 and the content height is 1242; while loading, the table and pager disappear, the skeleton leaves only 984 of content, and the browser clamps `scrollTop` to 203. With a shorter viewport or content, the content height drops below one screen and the clamp lands on 0, which is the top of the page. A visited page has cached data ready synchronously, never shrinks this way, and therefore does not reproduce.

## Decision

Query layer: `useOverviewCases` adds `placeholderData` and keeps the previous valid list result within the same workspace until the new query returns. The placeholder checks the `workspaceId` in the query key, so switching spaces never shows another space's data. This matches the existing `08 §6.2` rule that a filter change keeps the previous valid result until the new query returns.

Component layer: `BadCaseTable` shows the skeleton only on the first load with no rows. When data exists, paging or filter changes keep rendering the old rows, the list root carries `aria-busy`, and the pager info gains a "loading" hint. The pager stays visible and operable so rapid paging remains possible. The data layer still isolates pages by URL `page` and query key, so a late response for an old page writes only its own cache key and never replaces the current page.

## Alternatives considered

- **Disable the pager while loading**: keeps the current page in place but makes the control unusable during requests and blocks rapid paging; rejected.
- **Give the list a fixed minimum height**: reserves space but leaves a large blank area on a short last page, and only masks the height collapse instead of fixing the loading state that replaces the whole table; rejected.
- **Restore `scrollTop` after the request finishes**: smooths the visual result, but the person may scroll elsewhere during loading and the restore steals scroll control; it also leaves the root cause, removing content while loading, in place; rejected.
- **Overlay the skeleton absolutely on the old table**: needs extra positioning and masking, still hides readable old data, and is more complex than keeping the rows; rejected.

## Consequences

- Both the first-visit and cache-hit paging paths keep the list scroll position; old rows, pager, and page number stay visible while loading, and the refresh-like jump is gone.
- A short last page still shrinks to its real row count, so the browser may clamp `scrollTop` by a few rows, but it never jumps to the top; no fake whitespace is used.
- A failed request still replaces the list with the block-level error state and recovers after retry; a failed page has no current-page data to retain, so that path does not promise retained rows.
- No API, contract, ordering, page-size, or server-cache change, and no change to other overview blocks or the workspace shell's scroll ownership.
