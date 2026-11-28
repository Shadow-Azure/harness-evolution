# Agent Note: Top-align the evolution run list at content height

Status: implemented

English | [中文](2026-11-28-evolution-run-list-empty-alignment.md)

## Problem

With no evolution runs in the workspace, `/workspaces/<wid>/evolution` shows large vertical gaps between the page intro and "Running (0)", between group labels and their empty cards, and the two empty cards are much taller than a single-line hint needs ([GitHub #669](https://github.com/Shadow-Azure/harness-evolution/issues/669)).

The list root `.run-list-page` uses `display: grid`, and `main.css` gives it `height: 100%` plus `overflow-y: auto` so it owns page-level scrolling inside the fixed-height, overflow-hidden `.workspace-main` shell (#496). The grid container sets no `align-content`, so the default `normal` resolves to `stretch` whenever content is shorter than the container: the intro and the two groups split the free space as three auto tracks, and their items stretch with the rows. The empty card `.waiting` is a grid item inside a group and fills the stretched row through the default `align-items: stretch`.

Measured in the browser at width 1366 (list height 712 vs 1024): the intro grows from 179.8px to 283.8px, an empty card from 111.5px to 163.5px, and the intro-to-first-group gap from 145.9px to 249.9px. A 3/5 list has no free space, so the same code looks correct on long lists — which is why the gaps only appear on empty or sparse lists.

## Decision

`.workspace-main .run-list-page` keeps `height: 100%` and `overflow-y: auto` and adds `align-content: start`: the three auto tracks now sit at the content-box top at their content height, and leftover height stays at the bottom of the scroll container instead of being distributed into the tracks. Groups and cards keep their existing `gap` and content heights; the empty card keeps its own `15px 16px` padding and gets no fixed height.

At ≤640px the shell already hands height back to the document and the list uses `height: auto`, so the line does not change mobile scroll ownership; long lists already have no free space and keep their behavior.

## Alternatives considered

- **Remove `height: 100%` or switch to `min-height`**: this returns the list to document scrolling and breaks the page-level and narrow-screen scrolling contract established by #496; rejected.
- **Add only `align-items: start`**: this stops a single item from filling its row, but the auto tracks still split the free height and the gaps remain; rejected.
- **Give the empty card a fixed `height` or `max-height`**: this squeezes one state but clips wrapped hints, zoomed text, or future copy; rejected, so size stays content-driven.
- **Rewrite the page grid as flex or set every row to `min-content`**: larger surface with no benefit over the current `gap` and intro structure; rejected.

## Consequences

- On empty and sparse lists the intro, group labels, and empty cards flow from the top; at 1366×768 versus 1366×1080 the empty-card height and adjacent gaps no longer follow the viewport.
- The empty card stays about 51px tall instead of growing by a hundred pixels; both group labels, zero counts, hints, and the launch entry are unchanged.
- Long lists still scroll to the last card through the list root; mobile still scrolls the document without nesting a second scroll container.
- Only vertical alignment on the list container changes; run data, API, contracts, card fields, and the global shell are untouched.
