# Agent Note: Evolution-list page-level scrolling and the 1080px frame

Status: implemented

English | [中文](2026-11-22-evolution-list-page-scroll.md)

## Problem

The workspace shell fixes `main.workspace-main` to `height: calc(100vh - var(--shell-header-height))` with `overflow: hidden` and delegates scrolling to each page. The overview page's `.overview-page`, the workspace admin page's `.admin-page`, and the run detail's `.run-detail-page` all provide a `height: 100%; overflow-y: auto` page-level scroll container; the evolution list's root `.run-list-page` only reused `.evolution-page-frame`'s page width and padding and still declared only `display: grid; gap: 14px`. When the list grew to 3 running plus 5 history cards and 1348px of content, the 616px beyond `main`'s 732px visible height was clipped outright, the wheel, PageDown, End, and `window.scrollTo` did nothing, and the document's `scrollHeight` equaled its `clientHeight`. Production measurements are in GitHub #496.

The V2 prototype scrolls through the document and grows the page with its content; after the shell replaced document scrolling with a fixed viewport, the list page never completed the migration to the same contract and became the only list page without a page-level scroll entry. The 1080px page width and scrolling are separate concerns, and this decision only restores scroll ownership.

## Decision

- The list page root owns page-level scrolling: `apps/web/src/styles/main.css` declares `left: 0`, `width: 100%`, `height: 100%`, `margin: 0`, and `overflow-y: auto` for `.workspace-main .run-list-page`, with inline padding `max(24px, calc((100% - 1080px) / 2 + 24px))`, 20px top, and 64px bottom.
- The node stays full width, so a classic vertical scrollbar is painted at `main`'s window edge; the symmetric padding keeps the 1080px frame centered and preserves a content column of about 1032px (overlay scrollbar) or 1017px (classic 15px scrollbar) at a 1408 viewport, without shifting the first screen horizontally.
- At ≤640px it follows `main.workspace-main`'s `height: auto; overflow: visible` branch: the root switches to `height: auto; overflow-y: visible` and `8px 24px 0` padding, letting the document scroll and avoiding nested scrollbars.
- Only styles and the real-browser regression change; no template structure, card component, data flow, or launch-wizard change. `m5-run-list` asserts the single scroll container, a non-scrolling document, the scrollbar's right edge, content-column geometry, and reachability with a real wheel / PageDown / End at 1408×788, 1366×768, and 1920×1080, and asserts document scrolling at 390×844.
- The object configuration page (`pages/evolution/targets/Index.vue`) also lacks page-level scrolling, but this decision covers only `.run-list-page`; unifying both needs a separate issue and acceptance.

## Alternatives considered

- **Keep the 1080px frame width and only add `height: 100%; overflow-y: auto`**: smaller, but the scrollbar would sit inside the 1080px content column, about 164px from the window's right edge at a 1408 viewport, contradicting the placement already settled in #362/#423. Rejected.
- **Change `main.workspace-main`'s `overflow: hidden` to `overflow-y: auto`**: one line would give every page without its own scrolling a scrollbar, but it would move scroll ownership for the overview, Session, error-detail, and workspace-admin pages at once and require re-checking nested scrollbars, beyond this issue's local fix. Rejected.
- **Add an inner scrolling or content wrapper in the list template**: it needs another DOM layer and re-spacing, and only separates scrolling from page width; the root styles already satisfy both goals with a smaller change. Rejected.
- **Hide the scrollbar, compress card heights, or ask users to change zoom**: this only hides the clipping without restoring reachability and violates the issue's acceptance criteria. Rejected.

## Consequences

- The evolution list reaches the last history card at desktop viewports from 1366×768 through 1920×1080, the scrollbar sits at the window's right edge, and the content column stays where it was.
- The scroll implementations of the overview, workspace admin, run detail, Session browser, and object configuration pages are unchanged; the object configuration page can still clip content past the first screen and needs a separate issue.
- At ≤640px the document scrolls; if `main.workspace-main`'s mobile height / overflow branch changes later, the list page's breakpoint styles must follow.
- The real-browser suite's `m5-run-list` adds a scroll and content-column regression; it still uses the synthetic fixture and never reads production runs or user screenshots.
