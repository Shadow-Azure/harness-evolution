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

The captured page is already scrolled down as a whole: the left "Session browser" title, search and filters, and the right-hand Session title, stats and flow top edge are outside the capture. The red box is the page background band left below both columns.

## Production re-check and root cause

Around 15:00 on 2026-11-20 the same Session `5f4a5c96-d4bf-4781-b5c5-291c6b5b21ea` was re-checked against production (http://8.149.232.63/ with the administrator account):

- The deployed `assets/index-CYlO1h4q.js` has the same hash as a local `pnpm build` of main, ruling out a stale build or cache.
- At 1500×837, dpr 2: `document.scrollingElement.scrollHeight = 1895`, `clientHeight = 837` (about 2.26 screens), and the window scrollbar takes 15px.
- `.shell` is 837 tall; `main.workspace-main`, `.session-browser`, `.sidebar` and `.overview` are all 781 tall with bottom 837; the only qualifying `overflow-y: auto` scrollers are `.session-list` (1843 / 607) and `.overview` (952 / 781).
- No visible element extends past 837, yet hiding `.session-list` drops the document back to 837 immediately; hiding the Session cards one by one reduces the document height by one card height (about 179px) each time; the last card's `span.sr-only` sits at y≈1830, and the 1895 document height is exactly determined by it.

The root cause is the accessible status text in `apps/web/src/pages/sessions/components/SessionCard.vue`:

- `.sr-only` uses `position: absolute`, while `.session-card` and `.session-list` have no positioned ancestor, so the computed `offsetParent` is `body`.
- The absolutely positioned box's containing block is the initial containing block; `.session-list`'s `overflow-y: auto` is not in its containing-block chain, so the list **does not clip it**. Its static position (the card title row) is counted in the root element's scrollable overflow.
- With 10 production Sessions, the last card's `.sr-only` lands at y≈1830, stretching the document to 1895 while the visible layout stays 837. The browser therefore paints the window scrollbar, and the page can scroll into the blank band below the two columns. The user's third scrollbar and blank band both come from this.

Why it was missed before: the #415/#422 and m3 e2e synthetic data only has 4 Sessions; with 4 cards the last `.sr-only` is still inside 837, so the document stays 837. Production's 10 cards cross the viewport, so the #422 low-content fill never touched this overflow and the regression stayed green.

The fix was validated in-memory on the production page: setting `position: relative` on `.session-card` changes `document.scrollHeight` from 1895 to 837 immediately, `scrollWidth = clientWidth = 1500`, only `.session-list` and `.overview` remain as scrollers, and `window.scrollTo(0, 600)` keeps `scrollY` at 0. Before / after:

![Production re-check: document 1895 before the fix, window scrollbar present](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-prod-verify.png)

![Production re-check: document 837 after injecting the fix, only the left and right scrollbars](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-prod-fixed.png)

## Goals

- The production Session error view shows only the left list and right content vertical scrollbars at 1500×837, 1440×900 and 1366×768; the document does not scroll and cannot reach the blank band below the columns.
- Turn "document does not scroll plus exactly two scrollbars" into a regression assertion covering 10+ Sessions, so an absolutely positioned element without a positioned ancestor cannot stretch the document again.
- Audit the same `.sr-only` pattern so it does not reappear in other scroll containers.
- Do not change API contracts, Session data or content structure; do not change the V2 prototype.

## Design authority

- [08 §5.5 shell height and right-column fill](../../../plans/fullstack-design/08-frontend-implementation.md): `.session-browser` is fixed to the window height, the document does not scroll, and each column scrolls internally.
- V2 prototype `plans/ui-prototype-v2/harness-evolution.html` (`?u=admin&page=session&ws=ws-harness`): `.shell` is `calc(100vh / var(--ui-zoom) - 56px)`, the body has a fixed 56px top offset, `.session-list` and `.main` scroll internally, and the page itself does not scroll.
- Affected implementation: `apps/web/src/pages/sessions/components/SessionCard.vue` (`.sr-only`), `apps/web/src/pages/sessions/Index.vue` (`.session-browser`), `apps/web/src/pages/sessions/components/SessionOverview.vue` (`.overview`).
- Prior work: [#415](https://github.com/Shadow-Azure/harness-evolution/issues/415) recorded the blank band and window-level scroll on the same page; [#422](https://github.com/Shadow-Azure/harness-evolution/issues/422) (m22-02) fixed the low-content fill and added the "document does not scroll" regression, but its synthetic data has only 4 Sessions and does not cover this overflow.

## Comparison and reproduction

| Item | Production (measured) | V2 prototype | Current main (4-card fixture) |
|---|---|---|---|
| `document.scrollHeight` / `innerHeight` | 1895 / 837 | 837 / 837 | 837 / 837 |
| Vertical scroll containers | left list + right column + window | `.session-list` + `.main` | `.session-list` + `.overview` |
| Document scrollable | yes | no | no |
| Blank band below both columns | yes | no | no |

- V2 prototype at the same viewport (only the left and right bars; `document` 837 = viewport 837):

![V2 prototype at the same viewport: only two scrollbars](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-prototype.png)

- Current main at the same viewport with 4 fixture Sessions (`document` 837 = viewport 837):

![Current main at the same viewport: four Sessions, only two scrollbars](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-current-main.png)

## Implementation

- `SessionCard.vue`: add `position: relative` to `.session-card` so the card's `.sr-only` resolves its containing block to the card and is clipped again by `.session-list`'s `overflow-y: auto`; no visible layout or accessible text change.
- Audit the other `.sr-only` sites (`AttributionReport.vue`, `VersionLabel.vue`): where they sit inside a scroll container without a positioned ancestor, apply the same containment (add `position: relative` to the nearest card/row container, or place the `.sr-only` inside an already positioned wrapper); add a line to 08 §5.5 that an `.sr-only` inside a scroll container must have a positioned ancestor.
- `tests/e2e/m3-session-browser.test.mjs`: add a 10-Session list scenario (extend the fixture or seed the same way), and assert at 1500×837 and 1440×900:
  - `document.scrollingElement.scrollHeight === innerHeight`;
  - after `window.scrollTo(0, 500)`, `window.scrollY === 0`;
  - exactly two top-level `overflow-y: auto|scroll` containers with `scrollHeight > clientHeight + 1`, matching `.session-list` and `.overview`;
  - no `.session-card .sr-only` has `offsetParent === document.body` (direct lock on this root cause).
- Record the "an `.sr-only` inside a scroll container needs a positioned ancestor" contract and its verification in 08 §5.5 and the Agent Note in the same PR.
- Re-verify production after the fix with a hard refresh, with before/after screenshots and the build hash.

## Implementation steps

1. Add `position: relative` to `.session-card`; first validate on production by injecting it as above and confirming the document returns to 837.
2. Audit the other `.sr-only` sites and apply the same containment.
3. Extend m3 e2e with 10 Sessions: confirm it fails on the unfixed code, then passes after the fix.
4. Update 08 §5.5 and the Agent Note.
5. Run the gates, capture before/after screenshots, and re-verify production after a hard refresh.

## Dependencies and boundary

- Depends on m22-02 (the Session page fill and "document does not scroll" regression baseline).
- No API, data or Session content changes; no V2 prototype changes; production Session screenshots are not committed into the repository, evidence lives only in the issue/Release attachments.
- The fix needs a redeploy and a hard-refresh production acceptance; `position: relative` does not change the visible layout.

## Verification

```sh
pnpm typecheck:web
pnpm lint:web
pnpm test:web
node --test tests/e2e/m3-session-browser.test.mjs
pnpm verify:flow
pnpm lint:docs
```

- The e2e passes with 10 Sessions at 1500×837 and 1440×900: document height equals viewport height, `scrollY` stays 0, exactly two top-level vertical scroll containers qualify, and no `.sr-only` has `offsetParent === body`.
- After a hard refresh, production at the same viewport shows only the left and right scrollbars, with `document.scrollingElement.scrollHeight` equal to `innerHeight`.

## Acceptance

- The production Session error view shows only the left and right vertical scrollbars at 1500×837, 1440×900 and 1366×768, and the page does not scroll.
- The third bar does not return; the new 10-Session regression turns red on the unfixed code.
- Low-content, long-content and 10-Session states all hold; mobile ≤860px still scrolls the document normally.
- The other `.sr-only` sites are audited and the conclusion recorded.

## Gates and CI

- Hits `pnpm test:e2e` (m3 Session browser), `pnpm typecheck:web`, `pnpm lint:web`, `pnpm verify:flow`, `pnpm lint:docs`.
- The new assertions join the existing e2e case instead of adding a separate slow test.

## Non-goals

- No Session page re-layout, no column width or visual style changes.
- No `body { overflow: hidden }` style hiding of the third bar without fixing the root cause.
- No V2 prototype or other page changes (the run detail scroll container is tracked by [#423](https://github.com/Shadow-Azure/harness-evolution/issues/423)).
- No reopening or rewriting the closed #415 blank-band work.
