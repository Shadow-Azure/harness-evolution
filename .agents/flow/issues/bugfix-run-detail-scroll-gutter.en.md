# Run detail clips content without a scroll container and diverges from the V2 prototype page gutters

English | [中文](bugfix-run-detail-scroll-gutter.md)

```yaml flow
kind: issue
id: bugfix-01
milestone: bugfix
depends:
  - m21-01
priority: P2
status: ready
scope:
  - apps/web/**
  - tests/e2e/**
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr: []
github:
  number: 423
  url: https://github.com/Shadow-Azure/harness-evolution/issues/423
```

## Background

### Problem scenario

On common laptop viewports, the production "Evolution → Run detail" page is clipped as a whole: the page stops in the middle of the cluster list at "Step 5 · Clustering and severity", the content below is invisible, no vertical scrollbar appears, and the mouse wheel, PageDown, End, and `window.scrollTo` all do nothing; only browser zoom-out reveals more content. The screenshot's run stopped at the failed clone stage while viewing step 5; the same layout reproduces at 1366×768, 1440×900, and 1500×837, while 1920×1080 avoids vertical clipping only because the content height happens to fit the first screen, yet it is still full-bleed horizontally.

Reproduction path: `/workspaces/<wid>/evolution` → any run in history → run detail; set the browser viewport to 1500×837 (equivalent to the screenshot's 3000×1674 @2x).

### Measurements

On the production 1500×837 CSS viewport (same run, same step 5, computed styles read through Playwright):

| Viewport | `main` visible height | `.run-detail-page` content height | Overflow | `scrollY` after wheel | Document `scrollHeight` |
|---|---:|---:|---:|---:|---:|
| 1366×768 | 712 | 1006 | 294 | 0 | 768 |
| 1440×900 | 844 | 1006 | 162 | 0 | 900 |
| 1500×837 | 781 | 1006 | 225 | 0 | 837 |
| 1920×1080 | 1024 | 1006 | 0 | 0 | 1080 |

- `document.scrollingElement.scrollHeight === clientHeight`, so the document itself has no scrollable height; `main.workspace-main` has `scrollHeight` 1006 and `clientHeight` 781, but `overflow-y: hidden`; no descendant offers an `overflow-y: auto|scroll` scroll container. This is therefore not a "hidden scrollbar" problem: the page genuinely has no scrolling behavior.
- After the wheel, PageDown, End, and `window.scrollTo(0, 1000)`, both `window.scrollY` and every element's `scrollTop` stay at 0.
- The 1006px content height covers only the one cluster and expanded source bad case table already rendered for this run; more clusters or more expanded rows make the content taller and the clipping larger.

### V2 prototype comparison

Opening the run detail in `plans/ui-prototype-v2/harness-evolution.html` (`#/run/EV-20261109-01`, also at step 5) locally at the same 1500×837 viewport:

- The prototype scrolls through the document: `document.scrollingElement.scrollHeight = 1474`, `clientHeight = 837`; one wheel gesture sets `scrollY = 637`, and the page can scroll all the way to the bottom.
- The prototype content container `.evo-app .wrap` uses `width: min(100%, calc(1720px / var(--ui-zoom, 1)))`, `margin: 0 auto`, and `padding: 20px 24px 64px`; at 1500×837 the detail content starts at x=25 with width 1450; at 1440×900 it starts at x=24 with width 1392; at 1920×1080 the container is 1720 wide and centered, starting at x=130 with width 1660.
- Production has no such page container: `.run-detail-page` hangs directly under `main.workspace-main`, starts at x=0 with width 1500 at the 1500 viewport, and is 1920 wide at the 1920 viewport, so cards touch both edges; at the same viewport the production gutters are 0 while the prototype uses 24–25px (1500) and 130px (1920), the direct reason the screenshot "does not feel as comfortable as the V2 prototype".
- Production is also internally inconsistent: the same app's "Evolution" list, target configuration, and workspace administration use `.evolution-page-frame` (`width: min(1080px, 100%)` + 24px padding, starting at x=210 with width 1080 at the 1500 viewport); only the run detail has neither the 1080 frame nor the prototype's 1720 page width, making it a full-bleed outlier.

### Root cause

1. `main.workspace-main` in `apps/web/src/App.vue` pins workspace pages to `height: calc(100vh - var(--shell-header-height))` with `overflow: hidden`, so the document itself does not scroll; scrolling responsibility is delegated to each page.
2. `.overview-page` in `apps/web/src/pages/overview/Index.vue` and `.admin-page` in `apps/web/src/pages/workspaces/Admin.vue` honor that contract with a `height: 100%; overflow-y: auto` page-level scroll container; `.run-detail-page` in `apps/web/src/pages/evolution/RunDetail.vue` only declares `display: grid; gap: 14px`, with no height or scrolling declaration. Once the content exceeds `main`'s visible height, the excess is clipped by `main`, and with no second scroll container inside the page there is neither a scrollbar nor any scrolling.
3. `.run-detail-page` is not wrapped in `.evolution-page-frame` like the list, configuration, and administration pages, so it inherits `main.workspace-main`'s 100% width and zero padding and renders full-bleed. The m21-01 run detail re-layout changed the card hierarchy and content height but kept a root without a scroll container or page-width container; the current run is 1006px tall at 1500×837, exceeding `main`'s 781px.

### Impact

- The step-5 cluster list, step-6/7 content, and execution-log tab cannot be fully viewed on laptop viewports; users can only change browser zoom or switch to a larger display.
- The edge-to-edge layout diverges from both the rest of the app and the V2 prototype and raises visual density; the wider the viewport, the larger the gap from the prototype's 1720 page width.
- This is a front-end layout regression, not a data or execution-result issue; nothing except refreshing, switching browsers, or zooming out works around it.

## Goals

- The run detail scrolls vertically at common viewports such as 1366×768, 1440×900, and 1500×837; the wheel, PageDown, and End all reach the bottom of the page instead of being clipped by `main`.
- The run detail gains a page-level content container: by default the V2 prototype `.wrap` rules of `min(100%, 1720px)` plus 24px horizontal padding and centering, restoring prototype-consistent gutters; the scrollbar stays at the window edge instead of inside a card.
- The run detail's information hierarchy, field set, tabs, step content, and data semantics stay unchanged; the scrolling behavior of the Session browser, overview, workspace administration, and other pages stays unchanged.
- Component tests or E2E cover the two regression points, "scrollable" and "page gutters", so a future re-layout cannot again push content past the fold without a scroll container.

## Design authority

- [08 §10.1 run detail structure / §10.2 interaction](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L740-L800): the run detail is a single-column card flow containing the header, tabs, goal and input, flow progress, and current step output; step content can be long, so the page must scroll to the last cluster.
- [V2 prototype run detail](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L5423-L5446): `evRenderDetail()` puts the detail inside `.wrap`; [`.evo-app .wrap`](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L606) defines `width: min(100%, 1720px)`, `margin: 0 auto`, and `padding: 20px 24px 64px`, with the document providing scrolling.
- [V2 front-end prototype design §2.1](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/design-v2.md): the detail reuses the V1 panel/stepper/cluster components without introducing a second layout language.
- [Existing page-level scrolling implementation](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/web/src/pages/overview/Index.vue#L607-L615): `.overview-page` uses `height: 100%; overflow-y: auto` plus symmetric padding to keep the scrollbar at the window's right edge, the in-app pattern this issue should reuse.

## Implementation

- `apps/web/src/pages/evolution/RunDetail.vue`: turn `.run-detail-page` into a page-level scroll container with `height: 100%`, `overflow-y: auto`, and 64px bottom padding; use `max(24px, calc((100% - 1720px) / 2 + 24px))` for the horizontal padding so the content caps at 1720px and centers, while the scrollbar remains at `main`'s window edge.
- Adjust the narrow-screen breakpoint in `RunDetail` accordingly: at ≤640px reduce the horizontal padding to 12–16px to avoid double gutters on small screens; under `main.workspace-main`'s mobile `height: auto` branch, change `height: 100%` to `height: auto` or keep document scrolling (matching the overview mobile handling).
- Do not change the component's DOM hierarchy or data logic; prefer styling only the root node. If review requires an explicit content container, wrap the existing cards in a `.run-detail-inner`, but pick one approach in the PR and keep a single implementation.
- Regression tests: cover the page-level scroll container and content reachability in `apps/web/src/pages/evolution/RunDetail.test.ts` or a new E2E; at 1440×900 / 1500×837 the E2E asserts `.run-detail-page` has `scrollHeight > clientHeight`, `scrollTop > 0` and reaches the bottom after the wheel or End, and that the horizontal padding/content width follows the 1720 page-width rule.
- If the implementation keeps the existing `.evolution-page-frame` 1080 page width instead of the prototype's 1720, the PR must explain why and update this issue's acceptance wording; aligning to the prototype's 1720 is the default recommendation.

## Implementation steps

1. Add page-level scrolling and page-width padding to the `RunDetail.vue` root, confirm `main.workspace-main`'s `overflow: hidden` no longer clips content, and add a content wrapper in the template if needed.
2. Handle the ≤640px breakpoint and confirm mobile does not get double scrollbars from `height: 100%` plus document scrolling.
3. Add component/E2E assertions: the scroll container exists, content reaches the bottom, and the gutters at 1500/1920 match expectations.
4. Run a production-equivalent page locally and capture before/after screenshots plus scroll checks at 1366×768, 1440×900, 1500×837, and 1920×1080; label the before image with the current baseline revision.
5. Run focused unit tests, typecheck, lint, E2E, and the flow gate; attach the before/after comparison and measurements to the PR description.

## Dependencies and boundary

- Dependency: m21-01 (the run detail was already re-laid-out against the V2 prototype; this issue only fixes layout scrolling and page gutters, without reverting its fields or hierarchy).
- Delivery boundary: only the run detail styles and their tests under `apps/web`; no changes to the API, contracts, attribution/clustering/eval algorithms, SSE, seven-step keys, or step content components.
- Do not commit production run IDs, Session content, or production screenshots to the repository; before/after screenshots live only in the PR description or local evidence, not in fixtures.
- The list, target configuration, and workspace administration pages keep their 1080 page width; this issue does not change them incidentally. If the product decides to unify on the prototype's 1720, either open another issue or state that separate scope in this issue's PR.

## Verification

```sh
pnpm --filter @harness/web exec vitest run src/pages/evolution/RunDetail.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "m10-06"
pnpm verify:flow
```

- Open the production-equivalent run detail at 1500×837: `.run-detail-page` has `scrollHeight` greater than `clientHeight`; one wheel gesture gives `scrollTop > 0`; after End, the difference between `scrollTop + clientHeight` and `scrollHeight` is ≤2px.
- Measure the root node's horizontal padding at 1500×837 and 1920×1080: 24px at 1500 and 124–130px at 1920; the content width never exceeds 1720px.
- At 1366×768 and 1440×900 the page also scrolls to the bottom; the Session browser and overview show no double scrollbars and their scrolling behavior is unchanged.
- Unit tests, typecheck, lint, focused E2E, and `pnpm verify:flow` are all green.

## Acceptance

- At 1366×768, 1440×900, and 1500×837, the run detail scrolls with the wheel, PageDown, and End from the header to the last cluster and the bottom padding; `main` no longer clips content, and no "content taller than the viewport but without a scroll container" state remains.
- At 1500×837 the run detail has 24px on each side; at 1920×1080 the content area caps at 1720px and centers; compared with the V2 prototype at the same viewport, the gutter difference is ≤6px.
- The run detail's header, tabs, goal and input, flow progress, step output, and execution-log tab keep their order and fields; none of m21-01's acceptance items regress.
- Existing pages (Session browser, overview, workspace administration, evolution list/configuration) keep their scrolling behavior and page width.
- The fix PR carries before/after screenshots of the same scenario, viewport, and theme, with the before image labeled by baseline revision; no production screenshots are committed to the repository.
- Final acceptance is the requester's confirmation: this issue stays open until the requester confirms the whole flow currently has no problems; the fix PR delivers only the reviewable implementation and evidence.

## Gates and CI

- Unit tests and coverage: `pnpm test:web` (covering at least `RunDetail.test.ts`).
- Type and lint: `pnpm typecheck:web`, `pnpm lint:web`.
- E2E: `pnpm test:e2e -- "m10-06"`, adding this issue's scroll regression case when needed.
- Flow: `pnpm verify:flow`; the PR title and commits carry `(#<this issue number>)`.
- Docs: if design documents or the prototype change, also run `pnpm lint:docs`; by default neither changes.
- Deliver for human review after CI is green; a person merges this PR.

## Non-goals

- No changes to the run detail's DOM information hierarchy, field set, default tab, step keys, pagination, or execution-log data source.
- No changes to the API, `packages/contracts`, attribution/clustering/eval algorithms, SSE, or task scheduling.
- No V2 prototype rework, design-token changes, or unilateral 1080 page-width changes to the list/configuration/administration pages.
- No "fix" of the clipping by hiding scrollbars, using `overflow: clip`, or compressing content height.
- No production run IDs, Session content, screenshots, or credentials in the repository.
