# Third page scrollbar on the Session error view, diverging from the V2 prototype

English | [中文](bugfix-session-third-scrollbar.md)

```yaml flow
kind: issue
id: bugfix-02
milestone: bugfix
depends:
  - m22-02
priority: P2
status: ready
scope:
  - apps/web/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 434
  url: https://github.com/Shadow-Azure/harness-evolution/issues/434
```

## Background

On 2026-11-20 the user reported three vertical scrollbars on the production Session error view (`/workspaces/{wid}/sessions/{sid}`, 1500×837 CSS viewport): one for the left Session list, one for the right-hand content, and a third one at the far right of the window. The user asked to keep only the left and right scrollbars and remove the third.

User screenshot (1500×837 @2x):

![Production Session error view: three vertical scrollbars](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-problem.png)

Zooming into the right edge confirms that the third bar is the page (window) scrollbar, not a card-level scrollbar:

![Right edge zoom: the right-column scrollbar and the window scrollbar side by side](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-problem-right-edge.png)

Facts read from the screenshot:

- The page is already scrolled down as a whole: the left "Session browser" title, search and filters, and the right-hand Session title, stats and flow top edge are all outside the capture. The left list scrollbar track ends at y≈406, so the document itself scrolled by roughly 400–500px, which is not the left list scrolling internally.
- The window scrollbar at the far right pushes the `.overview` scrollbar about 17px to the left; the two grey scrollbars sit side by side. The window thumb covers about 353/837 of the track, implying a document about 1.5–1.9 viewports tall.
- The blank band outlined by the user below both columns is page background that remains after the two columns end, produced by the same document-level scroll.

This is not the intended scroll structure for this page. [08 §5.5](../../../plans/fullstack-design/08-frontend-implementation.md) fixes the root node to the viewport height, keeps the document itself from scrolling, and makes the left `.sidebar` and the right `.overview` the only scroll containers — exactly two bars. The V2 prototype at the same page and viewport also shows exactly two bars, see the comparison below.

## Goals

- The production Session error view shows only the left list and right content vertical scrollbars at common desktop viewports (at least 1500×837, 1440×900, 1366×768); the document does not scroll and cannot reach the blank band below the columns.
- Turn "document does not scroll plus exactly two scrollbars" from an implicit convention into a regression assertion, so the next breakage of the shell height chain turns the e2e red.
- Do not change API contracts, Session data or content structure; do not change the V2 prototype.

## Design authority

- [08 §5.5 shell height and right-column fill](../../../plans/fullstack-design/08-frontend-implementation.md): `.session-browser` is fixed to the window height, the document does not scroll, and each column scrolls internally; when the right column has less than one screen of content, the last problem list fills the remainder.
- V2 prototype `plans/ui-prototype-v2/harness-evolution.html` (`?u=admin&page=session&ws=ws-harness`): `.shell` is `calc(100vh / var(--ui-zoom) - 56px)`, the body has a fixed 56px top offset, `.session-list` and `.main` scroll internally, and the page itself does not scroll.
- Current implementation: `main.workspace-main` in `apps/web/src/App.vue`; `.session-browser` in `apps/web/src/pages/sessions/Index.vue`; `.overview` in `apps/web/src/pages/sessions/components/SessionOverview.vue`.
- Prior work: [#415](https://github.com/Shadow-Azure/harness-evolution/issues/415) recorded the blank band and the window-level scroll on the same page; [#422](https://github.com/Shadow-Azure/harness-evolution/issues/422) (m22-02) fixed the low-content fill and added the first "document does not scroll" e2e regression.

## Comparison and reproduction

Same page, same 1500×837 viewport, same low-content Session:

| Item | Production (user screenshot) | V2 prototype | Current main |
|---|---|---|---|
| `document.scrollingElement.scrollHeight` / `innerHeight` | about 1.5–1.9 × | 837 / 837 | 837 / 837 |
| Vertical scroll containers | left list + right column + window | `.session-list` + `.main` | `.session-list` + `.overview` |
| Document scrollable | yes (screenshot is scrolled) | no | no |
| Blank band below both columns | yes (red box) | no | no (right column fills) |

- V2 prototype at the same viewport (only the left and right bars; `document` 837 = viewport 837):

![V2 prototype at the same viewport: only two scrollbars](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-prototype.png)

- Current main at the same viewport (fixture Session; document 837 = viewport 837; only two bars):

![Current main at the same viewport: only two scrollbars](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-current-main.png)

Measured on current main (headless Chrome, 1500×837, fixture Session): `document.scrollHeight = 837 = innerHeight`, and only `.session-list` (scrollHeight 752 / clientHeight 607) and `.overview` (835 / 781) qualify as scroll containers. The prototype has `.session-list` (2237 / 554) and `.main` (824 / 756). Neither has a window scrollbar.

The production screenshot therefore does not match current main: it still carries the pre-#422 blank band, while #422 was deployed at 2026-11-20 13:17 with `1890e2d7`. The first step is to rule out a stale production build (hard refresh, record the build hash). Regardless of that outcome, the third scrollbar shows that this invariant currently relies on the implicit cooperation of the page height chain and has no explicit assertion.

## Implementation

- Give the Session page height a single owner: `main.workspace-main` provides the `100dvh` (`100vh` fallback) height and `overflow: hidden`; `.session-browser` uses `height: 100%` instead of recomputing `calc(100vh/dvh - var(--shell-header-height))`, keeping `min-height: 0`. The ≤860px single-column breakpoint stays `height: auto; overflow: visible` so mobile may scroll the document.
- Add explicit assertions to `tests/e2e/m3-session-browser.test.mjs`:
  - `document.scrollingElement.scrollHeight === innerHeight`;
  - after `window.scrollTo(0, 500)`, `window.scrollY === 0`;
  - walk all elements and require exactly two top-level scroll containers with `overflow-y: auto|scroll` and `scrollHeight > clientHeight + 1`, matching `.session-list` and `.overview`;
  - cover 1500×837, 1440×900 and the scrolled-to-bottom (long content) state.
- Update [08 §5.5](../../../plans/fullstack-design/08-frontend-implementation.md) and the Agent Note in the same PR with the "exactly two scrollbars, document does not scroll" contract and how it is verified.
- If production still reproduces after a hard refresh, collect `document.scrollingElement.scrollHeight`, `innerHeight`, every scroll container with its rect, and the build hash, then change the layout.

## Implementation steps

1. Reproduce with the production build (not the dev server) at 1500×837 and record the build hash; if a hard refresh makes it disappear, keep step 3 and step 4 and leave the layout unchanged.
2. Collapse the height source: `main.workspace-main` owns the viewport height and clipping, `.session-browser` uses `height: 100%`.
3. Add the m3 e2e assertions for "document does not scroll" and the scroll-container count.
4. Update 08 §5.5 and the Agent Note with "one bar on each side, no page scroll".
5. Run the gates, capture 1500×837 before/after screenshots (three bars → two), and re-verify production after a hard refresh.

## Dependencies and boundary

- Depends on m22-02 (the Session page fill and "document does not scroll" regression baseline).
- No API, data or Session content changes; no V2 prototype changes; production Session screenshots are not committed into the repository, evidence lives only in the issue/Release attachments.
- If the production re-check proves the screenshot came from a stale build, this issue still delivers steps 1, 3 and 4 (reproduction record, regression assertions, contract docs) and does not re-layout the page just to look different.

## Verification

```sh
pnpm typecheck:web
pnpm lint:web
pnpm test:web
node --test tests/e2e/m3-session-browser.test.mjs
pnpm verify:flow
pnpm lint:docs
```

- The e2e passes at 1500×837 and 1440×900: document height equals viewport height, `scrollY` stays 0, and exactly two top-level vertical scroll containers qualify.
- After a hard refresh, production at the same viewport shows only the left and right scrollbars; the build hash is recorded in the PR.

## Acceptance

- The production Session error view shows only the left and right vertical scrollbars at 1500×837, 1440×900 and 1366×768, and the page does not scroll.
- The third bar does not return; if it does, the e2e turns red.
- Both low-content and long-content states hold; mobile ≤860px still scrolls the document normally.
- The prototype comparison, the current-main reproduction record and the production build hash stay in the issue/PR.

## Gates and CI

- Hits `pnpm test:e2e` (m3 Session browser), `pnpm typecheck:web`, `pnpm lint:web`, `pnpm verify:flow`, `pnpm lint:docs`.
- The new assertions join the existing e2e case instead of adding a separate slow test.

## Non-goals

- No Session page re-layout, no column width or visual style changes.
- No V2 prototype or other page changes (the run detail scroll container is tracked by [#423](https://github.com/Shadow-Azure/harness-evolution/issues/423)).
- No `body { overflow: hidden }` style hiding of the third bar without fixing the height chain.
- No reopening or rewriting the closed #415 blank-band work.
