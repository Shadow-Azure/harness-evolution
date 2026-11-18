# Overview scrollbar sits on the content column's inner edge, about 160px from the window's right edge

English | [中文](m12-16-overview-scroll-ownership.md)

```yaml flow
kind: issue
id: m12-16
milestone: m12
depends:
  - m12-08
  - m12-09
  - m12-10
priority: P1
status: in-progress
scope:
  - apps/web/src/pages/overview/Index.vue
  - tests/e2e/m8-04-overview.test.mjs
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
adr: []
github:
  number: 362
  url: https://github.com/Shadow-Azure/harness-evolution/issues/362
```

## Background

On the production overview page on 2026-11-18, at a 1500×837 CSS viewport, 2× DPR, and with classic always-visible scrollbars, the vertical page scrollbar did not sit at the browser window's right edge. It sat at the right edge of the 1180px content column, leaving an approximately 160 CSS px blank band on the right; the user reported the problem and outlined that position.

Rendering `plans/ui-prototype-v2/harness-evolution.html` at the same viewport gives the comparison: the prototype scrolls the whole document, `documentElement.scrollHeight` is 1391 and `clientHeight` is 837, the content column `.v2-page .wrap` is `min(100%, 1720px)` wide and fills the available width, and the scrollbar sits at the window's right edge `x=1485–1500`. The current implementation pins the workspace main to `height: calc(100vh - 56px)` with `overflow: hidden` (`apps/web/src/App.vue` lines 116–121), so the overview page's inner `.overview-page` owns scrolling; that container is `width: min(1180px, 100%)`, `margin: 0 auto`, `overflow-y: auto` (`apps/web/src/pages/overview/Index.vue` lines 597–603), so the scrollbar is painted at the content column's right edge `x=1326–1338`, 160px from the window's right edge. The scrollbar also starts below the 56px top bar instead of at the window top.

The difference is reliably visible only where scrollbars are always shown. macOS overlay scrollbars hide while idle, which is why earlier production/prototype evidence screenshots did not expose it; on Windows or in a browser configured to always show scrollbars, the inset scrollbar is permanently visible.

## Goals

- Return the overview page's vertical scrollbar to the browser window's right edge, matching the V2 prototype's scroll ownership.
- Keep the 1180px content column centered, and keep card widths and the current information architecture unchanged.
- When the scrollbar appears, leave no interactive blank band to the right of the content column, and introduce neither horizontal scrolling nor a second scrollbar.
- Do not regress the 1024px single-column breakpoint or the 640px mobile behavior.

## Evidence screenshots

**Same-viewport scrollbar position comparison (1500×837 CSS, 2× DPR)**

[![Overview scrollbar position: V2 prototype versus current implementation](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-16-scrollbar-evidence/scrollbar-corner-compare.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-16-scrollbar-evidence/scrollbar-corner-compare.png)

**Full-page comparison (top: V2 prototype; bottom: current implementation)**

[![Overview full-page comparison](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-16-scrollbar-evidence/scrollbar-full-compare.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-16-scrollbar-evidence/scrollbar-full-compare.png)

Raw screenshots: [V2 prototype](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-16-scrollbar-evidence/proto-overview-1500x837.png) · [current implementation](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-16-scrollbar-evidence/app-overview-1500x837.png). Both raw screenshots were taken at 1500×837 CSS, 2× DPR, with `--disable-features=OverlayScrollbar`; the current implementation came from the locally running current frontend (Vite dev server) and seed data, and its layout matches production.

## Design authority

- [08 §6 Workspace overview page (`pages/overview/Index.vue`, V2)](../../../plans/fullstack-design/08-frontend-implementation.md#6-工作空间总览页pagesoverviewindexvuev2): the overview page's structure, interactions, and three states.
- [V2 design §5 Workspace overview](../../../plans/ui-prototype-v2/design-v2.md#5-工作空间总览): the prototype's conventions for metrics, filters, the dual view, and drill-down.
- [V2 prototype overview](../../../plans/ui-prototype-v2/harness-evolution.html): `.v2-page .wrap { width: min(100%, 1720px); margin: 0 auto }`, scrolling the whole document.
- [App.vue workspace shell](../../../apps/web/src/App.vue): `main.workspace-main` has a fixed height and hides overflow, which is where the inner scroll container comes from.

## Implementation

- Move vertical scrolling responsibility from `.overview-page` to the full-width workspace main (or equivalently return scrolling to the document), so the scrollbar is painted at the window's right edge; `.overview-page` keeps only the centered 1180px content column and its padding.
- Keep the fixed top bar and the `height: calc(100vh - 56px)` available height; the scroll area must not extend above the top bar, and there must be neither a second scrollbar nor horizontal scrolling.
- Synchronize `main.workspace-main`'s height/overflow in `App.vue` with the overview page's scroll container so `overflow: hidden` does not clip the scrollbar.
- Add an E2E assertion at a 1500×837 viewport: the overview scroll container's right edge equals `window.innerWidth` (±1px), the page still scrolls vertically to the list bottom, and the 1024px/640px breakpoints do not regress.
- Do not change data, APIs, URL state, or filter logic; if a shell change unavoidably affects other workspace pages, add regression evidence in the same PR.

## Implementation steps

1. Reproduce at 1500×837 and record the geometry gap between `.overview-page`, the scroll container, and the window's right edge.
2. Adjust scroll ownership between the workspace shell and the overview page while keeping the 1180px content column and current card widths.
3. In `tests/e2e/m8-04-overview.test.mjs`, assert that the scrollbar's right edge is flush with the window, and verify that the list scrolls and there is no horizontal overflow.
4. Re-capture the V2 prototype and the implementation at the same viewport with an always-visible-scrollbar browser as the PR's Before/After evidence.
5. Run the focused E2E, type checks, and lint, then follow `docs/review.md` for PR review.

## Dependencies and boundary

- The overview page body was delivered by m8-04, and the page header, filters, and list by m12-08, m12-09, and m12-10; this problem needs no new API, data field, or permission.
- Delivery boundary: change only the overview page's scroll ownership plus the corresponding tests/evidence; do not change the 1180px content column width, card structure, data, or APIs.
- If a shared shell change unavoidably affects the inner scrolling of the Session error view or the evolution page, explain it in the same PR and add matching regression evidence; do not silently expand this into a site-wide layout refactor.

## Verification

```sh
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- --pattern m8-04-overview
```

- Expected: type check and lint pass; the E2E at the 1500×837 viewport asserts that the overview scroll container's right edge equals the viewport's right edge, the list scrolls, and the 1024/640 breakpoints do not regress.
- Manual verification: re-capture the prototype and implementation at the same viewport in an always-visible-scrollbar browser; both scrollbars are flush with the window's right edge.

## Acceptance

- At 1500×837 with always-visible scrollbars, the overview page's vertical scrollbar is flush with the window's right edge, with no approximately 160px blank band on the right.
- The scrollbar starts where the prototype's does (below the top bar through the window bottom), and neither a second scrollbar nor horizontal scrolling appears while scrolling.
- The content column is still 1180px and centered; card, filter, and list widths and interactions are unchanged.
- The 1024px single-column breakpoint and the 640px mobile layout do not regress.
- The PR contains refreshed same-viewport Before/After comparison screenshots.

## Gates and CI

- `pnpm test:e2e -- --pattern m8-04-overview`
- `pnpm typecheck:web`, `pnpm lint:web`
- PR title and commit messages contain `(#N)`; review follows `docs/review.md`.

## Non-goals

- Do not redo the overview visuals, and do not adjust the 1180px content column width or card density.
- Do not change scrollbar styling (native/overlay, width, color).
- Do not change the scroll layout of the Session error view, evolution, workspace management, or other pages; any side effect from the shared shell must be explained within this issue's verification scope.
- Do not address data volume, API, or permission differences.
