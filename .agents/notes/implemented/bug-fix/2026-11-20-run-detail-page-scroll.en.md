# Agent Note: Run-detail page-level scrolling and V2 page width

Status: implemented

English | [中文](2026-11-20-run-detail-page-scroll.md)

## Problem

The workspace shell fixes `main.workspace-main` to `height: calc(100vh - var(--shell-header-height))` with `overflow: hidden` and delegates scrolling to each page. The overview page's `.overview-page` and the workspace admin page's `.admin-page` both provide a `height: 100%; overflow-y: auto` page-level scroll container, but the run detail's `.run-detail-page` only had `display: grid; gap: 14px`. At 1366×768, 1440×900, and 1500×837 the run detail content is about 1018px tall while `main` exposes only 712–844px, so the content below is clipped, the mouse wheel, PageDown, End, and `window.scrollTo` cannot move it, and no vertical scrollbar appears.

The run detail also inherited `main`'s 100% width and zero inline padding, so its cards touched both window edges; the sibling list/config/admin pages use the 1080px `.evolution-page-frame`, while the V2 prototype uses the 1720px `.evo-app .wrap`, leaving the run detail as an outlier against both layouts. The production scenario and measurements are in GitHub #423.

## Decision

- The run-detail root `.run-detail-page` owns page-level scrolling: `height: 100%`, `overflow-y: auto`, inline padding `max(24px, calc((100% - 1720px) / 2 + 24px))`, 20px top, and 64px bottom. It stays full width, so the classic vertical scrollbar is painted at `main`'s window edge; the content column caps at 1720px and centers, matching the V2 prototype's `.evo-app .wrap` (`width: min(100%, 1720px)`, `padding: 20px 24px 64px`) at the same viewport.
- At the ≤640px breakpoint the page follows `main.workspace-main`'s `height: auto; overflow: visible` branch: the root switches to `height: auto; overflow-y: visible` and `14px 12px 48px` padding, letting the document scroll and avoiding nested scrollbars.
- Only root styles change; no content wrapper, DOM hierarchy, field set, tab, or step component changes. A comment on the run-detail root records the scroll ownership and the 1720px page-width convention.
- E2E asserts at 1366×768, 1440×900, 1500×837, and 1920×1080 that the scroll container's right edge equals the window, inline gutters are 24/124px, the content column is ≤1720px, and `scrollHeight > clientHeight`, then reaches the bottom with a real wheel, PageDown, and End. At 640px it asserts document scrolling with no second scroll container on the root.

## Alternatives considered

- **Reuse `.evolution-page-frame`'s 1080px page width**: consistent with the sibling list/config/admin pages, but the run detail is a seven-step card flow containing wide tables, cluster cards, and diffs; 1080px would visibly compress the reading width. The issue's design basis explicitly points at the V2 prototype's 1720px, which still leaves a 24px gutter at a 1500 viewport. Rejected.
- **Switch `main.workspace-main` to document scrolling (drop the fixed height and `overflow: hidden`)**: this would move scroll ownership for the overview, workspace admin, and Session pages at the same time, beyond this issue's delivery boundary. The run detail reuses the full-width inner scroll container already proven on the overview page. Rejected.
- **Hide the scrollbar, use `overflow: clip`, or compress content height**: this hides clipping without restoring reachability, which the issue explicitly forbids. Rejected.
- **Add a `.run-detail-inner` content wrapper for the page width and padding**: this needs an extra template layer and re-spaces every direct child; the root styles are sufficient and keep the change surface minimal. Rejected.

## Consequences

- The run detail can reach the last cluster, steps 6/7, and the log tab on laptop viewports; the scrollbar sits at the window edge and the inline gutters differ from the V2 prototype by at most 6px at the same viewport.
- Scrolling and page widths for the overview, Session browser, workspace admin, and evolution list/config pages are unchanged; those pages keep 1080px, and unifying them at 1720px needs a separate issue and product confirmation.
- At 1920×1080 the content plus top/bottom padding is about 1102px against `main`'s 1024px, so that viewport now scrolls as well; this is the expected effect of restoring the page container, not a regression.
- At ≤640px the document scrolls; if `main.workspace-main`'s mobile height/overflow branch changes later, this page's breakpoint styles must follow.
- The real-browser suite adds a scroll and gutter regression case under `m10-06`; it still uses the synthetic fixture and never reads production runs or Session content.
