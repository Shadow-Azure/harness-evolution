# Keep the cluster preview compact and unify detail-page status

English | [中文](bugfix-cluster-preview-detail-layout.md)

```yaml flow
kind: issue
id: bugfix-76
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - apps/web/src/pages/evolution/**
  - apps/web/src/styles/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-28-cluster-preview-detail-layout.md
github:
  number: 674
  url: https://github.com/Shadow-Azure/harness-evolution/issues/674
```

## Background

A user screenshot shows the back entry, title, mode note, and preparation hint stretched far apart on the "Evolution → Cluster only" preparing page, which fills the viewport even with little content; the orange mode note and the preparation hint repeat the same flow. The `ClusterPreview.vue` root, like the run detail root, uses `display: grid` + `height: 100%` to own page scrolling but does not set `align-content`; by default the grid distributes free space across auto rows, so track heights and block gaps grow with the viewport on short content. `RunDetail.vue` uses the same layout declarations in its low-content state and must be checked for the same mechanism.

The status area also repeats itself: the top `status-banner` already names the state with a "preparing" badge and progress copy, while the `preparing` card repeats nearly the same copy under a second title. The mode note uses a large orange warning card, which is too heavy for a normal selectable mode. The long object name in the single-line chip next to the title has no wrap or truncation contract, so narrow screens can overflow horizontally.

## Goals

- Lay out the cluster page's back entry, title, mode note, status area, and result cards from the top at content height, leaving remaining space below the content; keep page-level scrolling and scrolling to the last of multiple clusters.
- At a fixed width, font, and zoom, grow the viewport height from 768 to 1080 with the short status card and adjacent gaps changing by no more than 2 CSS px.
- Keep one primary status area while preparing; turn the normal mode note into a compact info strip instead of a large orange warning card.
- Derive status copy from the real `run.progress` fields and existing tokens, never fake progress; preserve pause, resume, retry, and launch conditions with understandable disabled reasons.
- Wrap long object names and expose the full value on hover; no horizontal overflow on narrow screens or with long names.
- Keep the run detail page top-aligned on low content so the shared layout declarations do not regress.

## Design authority

- [08 §11 Cluster-only page](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#11-仅聚类页pagesevolutionclusterpreviewvue): banner copy, input summary, cluster list, and the page-scroll contract; cluster-only runs never generate patches or evaluate.
- [08 §10 Run detail page](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#10-运行详情页pagesevolutionrundetailvue): the header, status badge, info panels, and progress density this issue aligns with.
- [V2 prototype](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html): header, panels, and cluster cards flow from the top in normal document flow instead of filling the viewport; the cluster page reuses the run detail step-5 cluster components.
- [#669](https://github.com/Shadow-Azure/harness-evolution/issues/669): the evolution list already fixed the same grid stretch with `align-content: start`; this issue follows that conclusion instead of exploring the layout again.

## Implementation

- `apps/web/src/pages/evolution/ClusterPreview.vue`: keep `height: 100%`, `overflow-y: auto`, and the 1720px content column on the root and add `align-content: start` so auto rows sit at the top at content height; the ≤640px breakpoint still hands scrolling back to the document.
- Status semantics: the header badge and a single status area carry the state; stop rendering the duplicate `preparing` card, and take the status detail from `run.progress.stageLabel` (falling back to the real five-step flow description while preparing); show failure, blocked, and interrupted reasons inside the status area instead of repeating a second title.
- Turn the mode note into a compact info strip: keep "cluster analysis only, no patch generation or evaluation iteration" and the launch button, drop the large orange fill and bold warning, and use the existing `--border` / `--bg-panel` / `--text-dim` tokens.
- Long object names: allow the header to wrap, give `target-chip` `max-width: 100%` and `overflow-wrap: anywhere`, and expose the full value through `title`.
- `apps/web/src/pages/evolution/RunDetail.vue`: add `align-content: start` to its root so a low-content header, info cards, and progress block do not stretch with the remaining height; do not change its fields, tabs, or step content.
- Tests: cover `ClusterPreview` states (preparing/running/paused/blocked/failed/interrupted/completed, zero and multiple clusters, a long object name, and a read-only user), and add a browser geometry regression at 1366×768, 1366×1080, 1920×1080, and 390×844 that asserts top alignment and viewport-height-independent short-status-card height and gaps, keeping multi-cluster scrolling and no-horizontal-overflow checks.

## Implementation steps

1. Reproduce the preparing-page stretch with synthetic run data and record computed styles, element bounds, and duplicate copy.
2. Add the failing browser geometry regression and component state assertions first, then fix alignment, merge the status area, and tighten the mode note.
3. Regress the low-content run detail, multiple clusters, long object names, and narrow screens, and capture same-viewport before/after screenshots.
4. Sync the design document, Agent Note, and flow status, then run focused unit tests, type checks, lint, style, E2E, and flow gates.

## Dependencies and boundary

- Dependencies: none blocking; related to #669 and the scrolling issue #496.
- Boundary: only the cluster page and run detail root vertical layout, status presentation, matching tests, and design notes; no changes to clustering algorithms, APIs, contracts, state machines, evaluation timeouts, or other pages.
- Never commit production run IDs, Session content, or production screenshots; before/after screenshots stay in the PR description or local evidence.

## Verification

```sh
pnpm --filter @harness/web exec vitest run src/pages/evolution/ClusterPreview.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm verify:web-style
pnpm test:e2e -- --pattern cluster
pnpm verify:flow
```

- The new geometry regression fails before the fix and passes after it; at 1366×768 versus 1366×1080 the short status card height and adjacent gaps differ by ≤2 CSS px, content starts at the scroll container's content box, and the remaining space sits below the content.
- The preparing page shows exactly one primary status area with copy from `progress.stageLabel`; a multi-cluster page scrolls to the last cluster; 390×844 scrolls with the document and has no horizontal overflow.
- Type, lint, style, documentation, and flow gates pass; the PR includes same-viewport before/after screenshots and geometry measurements.

## Acceptance

- At a fixed width, font, and zoom, growing the viewport height from 768 to 1080 changes the short status card height and block gaps by ≤2 CSS px; remaining space is below the content.
- The preparing flow has one primary status area, and the normal mode note is not a large warning card.
- Existing detail-page tokens are reused; narrow screens and long names do not overflow horizontally.
- Pause, resume, retry, permissions, and launch behavior do not regress; multiple clusters scroll to the end.
- The low-content run detail page is also top-aligned; the PR provides same-viewport before/after screenshots and geometry assertions.

## Gates and CI

- The focused component test and browser geometry regression run in the existing CI; frontend unit tests, types, lint, style, documentation, and flow gates pass with coverage at or above 80%.

## Non-goals

- No changes to clustering algorithms, APIs, state machines, or evaluation timeouts.
- Do not mask the problem with fixed card heights, global zoom, decoration, or hidden necessary information.
- Do not rearrange the run detail fields, tabs, or step content, and do not change the global shell.
