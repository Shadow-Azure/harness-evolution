# Agent Note: Top-aligned cluster preview with one status area

Status: implemented

English | [中文](2026-11-28-cluster-preview-detail-layout.md)

## Problem

The "Evolution → Cluster only" preparing page stretches vertically when it has little content: large gaps open between the back entry, title, mode note, and preparation hint, and the status copy appears both in the top status bar and in the preparation card ([GitHub #674](https://github.com/Shadow-Azure/harness-evolution/issues/674)).

The `.cluster-preview-page` root, like `.run-detail-page`, uses `display: grid`, `height: 100%`, and `overflow-y: auto` to own page scrolling inside the fixed-height `.workspace-main`, but does not set `align-content`. The grid default `normal` behaves like `stretch` when the auto rows are shorter than the container, so a short status page's rows are stretched and element gaps grow with the viewport height. Browser measurements at 1366 wide: the preparing status area grows from 114.2px to 176.6px, the mode strip from 126.5px to 188.9px, and only 64px of space remains below the content at 768 high; after the fix the 1366×768 and 1366×1080 values differ by ≤2px. A completed page with long content has no free space, so the symptom appears only in short states such as preparing or failed.

The duplicate status comes from the template: `status-banner` already names the state with a "preparing" badge and `statusDetail`, and the `preparing` card repeats nearly the same copy under a second title. The orange `.banner` uses a warning card for the normal "cluster analysis only" mode note, which is too heavy. `target-chip` has no width limit, so a long object name overflows horizontally on narrow screens.

## Decision

- Keep `height: 100%`, `overflow-y: auto`, and the 1720px content column on `.cluster-preview-page` and add `align-content: start`, so auto rows sit at the content-box top and the remaining height stays at the bottom of the scroll container. `.run-detail-page` gets the same declaration so its low-content header, info cards, and progress block no longer stretch.
- Keep one primary status area: the title row shows the status badge (matching run detail), and the status area shows the real `progress.stageLabel` plus failure or blocked reasons. Do not render a second preparation card, and do not invent a percentage or turn count.
- Turn the mode note into a neutral info strip: keep "cluster analysis only, no patch generation or evaluation iteration" and the launch button, drop the orange warning fill and bold emphasis, and use `--border` / `--bg-panel` / `--text-dim`.
- Let `target-chip` wrap (`max-width: 100%`, `overflow-wrap: anywhere`) and expose the full value through `title`.

## Alternatives considered

- **Remove `height: 100%` or use `min-height`**: the page would rejoin document scrolling inside the shell, breaking the #496 page-scroll and window-edge scrollbar contract; rejected.
- **Add only `align-items: start`**: this stops a single item from stretching inside a row, but auto rows still split the remaining height, so bands between rows remain; rejected.
- **Fix the status card height**: this compresses one state but truncates copy when text wraps, the font scales, or error details grow; rejected, dimensions stay content-driven.
- **Shrink the preparation card**: it would still duplicate the status bar's flow copy; rejected in favor of one status area.
- **Keep the orange mode card and only reduce padding**: the warning color still frames a normal mode as exceptional; rejected in favor of a neutral info strip.

## Consequences

- Short states such as preparing and failed lay out from the top; at 1366×768 and 1366×1080 the status card height and adjacent gaps no longer follow the viewport height, and the remaining space sits below the content.
- The page shows one preparation status area; the mode note and launch button remain but no longer occupy a large orange warning block.
- Long object names wrap and expose the full value on hover; multiple clusters still scroll to the last one through the root, and ≤640px still scrolls with the document.
- Only the vertical alignment of the two detail-page roots and the cluster page's status presentation change; no run data, API, contract, or clustering flow changes.
