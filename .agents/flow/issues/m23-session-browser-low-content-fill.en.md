# Fill the Session page viewport at low content

English | [中文](m23-session-browser-low-content-fill.md)

```yaml flow
kind: issue
id: m23-01
milestone: m23
depends:
  - m3-01
priority: P2
status: in-progress
scope:
  - apps/web/src/pages/sessions/**
  - tests/e2e/**
  - plans/**
  - .agents/**
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/implemented/bug-fix/2026-11-20-session-browser-viewport-fill.md
github:
  number: 422
  url: https://github.com/Shadow-Azure/harness-evolution/issues/422
```

## Background

On 2026-11-20 the production "Session error view" page showed a large page-background band below the content for a Session with only 1 user turn, 1 message, 0 tool calls, 0 sub-agents, and 1 bad case; the V2 prototype at the same viewport has no such band. The full comparison and captures are in [GitHub #415](https://github.com/Shadow-Azure/harness-evolution/issues/415).

The current main Session shell already fixes its height to `100vh - header`, the document does not scroll, and the problem list scrolls inside the right column, so a synthetic Session of the same size does not reproduce the full-page scroll and 300–550px band in the production capture. Two remaining gaps do reproduce on current main: `.overview` fills the column, but its content still ends at natural height above the bottom when shorter than the viewport, leaving blank in the right column background; and the execution flow is an async chunk that renders nothing until it arrives, so the column first collapses to a header-only panel with no placeholder above the problem list. The first appears on taller viewports or when the flow fails or is absent; the second appears briefly on every first paint.

## Goals

- The Session page root owns the viewport height: `100dvh` (with a `100vh` fallback) minus the shell header; the document itself does not scroll, while the left and right columns scroll internally.
- When the right column is shorter than one screen, the trailing problem list fills the remaining height; when content is taller, the list keeps its natural height and the right column scrolls. Problem-card bodies are not stretched.
- All five flow states — request loading, request failure, no data, async chunk loading, and chunk failure — keep a prototype-scale full-height placeholder, so the right column never ends early while the flow is not ready.
- Both 1500×837 and 1500×1100 have regression assertions; the ≤860px single-column mobile layout does not regress.
- No API contract, Session data, or problem-card content structure changes.

## Design authority

- [08 §5.5 Shell height and right-column fill](../../../plans/fullstack-design/08-frontend-implementation.md): the viewport height of `.session-browser`, scroll ownership, right-column fill, and the flow placeholder.
- [08 §5.1–5.2 Component tree and interactions](../../../plans/fullstack-design/08-frontend-implementation.md): responsibilities of the left column, right column, execution flow, and problem list.
- V2 prototype `plans/ui-prototype-v2/harness-evolution.html`: `.shell` fixes the viewport height, `.sidebar` and `.main` fill it, `.rf-canvas` uses `clamp(420px, calc(100vh - 280px), 720px)`, and `.finding-list` keeps 24px bottom padding.
- [GitHub #415](https://github.com/Shadow-Azure/harness-evolution/issues/415): production capture and difference comparison.

## Implementation

- `apps/web/src/pages/sessions/Index.vue`: add a `100dvh` height to `.session-browser` (keeping the `100vh` fallback) and `min-height: 0`; add `min-height: 0` to the right-column fallback error state.
- `apps/web/src/pages/sessions/components/SessionOverview.vue`: make `.overview` a column flex container with `min-height: 0`; `.overview-content` fills the available height; the trailing `.problem-list` uses `flex: 1 0 auto` to fill the remaining height when content is short; the top-level skeleton / error and empty states also participate in the fill.
- Same component: add loading / error components to the async AgentFlow chunk; use one `.tree-loading` placeholder at 720px desktop and 420px narrow for request loading, failure, and no-data; a failed chunk shows a failure message instead of blank.
- `tests/e2e/m3-session-browser.test.mjs`: fold the low-content layout assertions into the existing Session browser case, asserting that at 1500×837 the document does not scroll, both column bottoms match the viewport, and the last content after scrolling to the bottom is within 24px of the viewport bottom; after switching to 1500×1100, the problem list fills the remaining height with the same 24px spacing.
- Sync the shell and fill rules in `plans/fullstack-design/08-frontend-implementation.md`, the V2 prototype, and the Agent Note.

## Implementation steps

1. Fix the Session page shell height and keep both columns scrolling internally, not the document.
2. Make the right column a fillable column flex container so the trailing problem list fills the remaining height at low content.
3. Add the full-height placeholder for the flow async chunk, request loading, failure, and no-data states.
4. Add the 1500×837 and 1500×1100 low-content regressions in `tests/e2e/m3-session-browser.test.mjs`.
5. Update the design document, V2 prototype rules, and Agent Note; produce Before / After and prototype-reference evidence.

## Dependencies and boundary

- Depends on m3-01 (Session browser skeleton).
- Do not change the Session list / overview API, data semantics, problem-card content structure, or attribution pipeline.
- The full-page scroll in the production capture does not reproduce on current main; this change fixes the reproducible right-column collapse and low-content fill. Production build-hash and deployment confirmation are outside this issue's code delivery.
- Do not commit production Session content or screenshots to the repository.

## Verification

```sh
pnpm typecheck:web
pnpm lint:web
pnpm test:web
node --test tests/e2e/m3-session-browser.test.mjs
pnpm verify:flow
pnpm lint:docs
```

- `typecheck:web`, `lint:web`, and `test:web` pass.
- The low-content E2E at 1500×837 reports `document.scrollingElement.scrollHeight === innerHeight`; the bottoms of `.session-browser`, `.sidebar`, and `.overview` equal `innerHeight`; after scrolling the right column to the bottom, the problem-list bottom is 0–24px above the viewport bottom; at 1500×1100 the problem list is 0–24px above the viewport bottom directly.
- The E2E case fails before the fix at the 1500×1100 assertion (measured 108.5px gap) and passes after it (about 18px gap).

## Acceptance

- 1500×837, 1 turn / 1 message / 0 tools / 0 sub-agents / 1 case: no window-level scrollbar; the left Session panel and right content area fill the viewport; after scrolling the right column to the bottom, the last content is within 24px of the viewport bottom, with no 300–550px band.
- 1500×1100, same-size Session: the problem list fills the remaining height and the last content is within 24px of the viewport bottom.
- While the flow chunk is pending, while the request loads, after a request failure, and with no data, the right column keeps a full-height placeholder and does not collapse to a header-only panel.
- Multi-agent Sessions, problem-list scrolling, flow switching, and the 390×844 single-column layout do not regress.
- The PR description contains the production Before capture, the fixed After capture, and the same-region V2 prototype reference.

## Gates and CI

- `pnpm typecheck:web`, `pnpm lint:web`, `pnpm test:web`.
- `node --test tests/e2e/m3-session-browser.test.mjs` and the full CI E2E suite.
- `pnpm verify:flow`, `pnpm lint:docs`, `pnpm verify:web-style`.
- Commit and PR titles carry this issue's `(#N)`; the PR is linked to the M23 milestone.

## Non-goals

- Do not change Session list / overview query parameters, statistics semantics, or problem-card bodies.
- Do not stretch problem cards or reflow card content to fill space.
- Do not disable global `body` scrolling, which would affect overview and evolution pages that need document scrolling.
- Do not commit production Session content or screenshots to the repository.
