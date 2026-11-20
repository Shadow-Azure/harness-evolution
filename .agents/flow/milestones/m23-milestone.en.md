# M23 Session Page Low-Content Fill and Prototype Alignment

English | [中文](m23-milestone.md)

```yaml flow
kind: milestone
id: m23
title: M23 Session 页低内容填充与原型对齐
status: active
github:
  number: 33
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/33
```

## Goals

Keep the Session browser viewport behavior aligned with the V2 prototype for the low-content scenario reported in production: the page shell is fixed to the window height, both columns fill it and scroll internally, and the document itself does not scroll. When the right column is shorter than the viewport, its last block fills the remaining height, and the execution-flow area keeps a prototype-scale full-height placeholder while loading, after a failure, or when absent, so no full-width page-background band remains at the bottom.

## Scope

The shell and right-column containers under `apps/web/src/pages/sessions/`, the low-content regression in `tests/e2e/m3-session-browser.test.mjs`, §5 of `plans/fullstack-design/08-frontend-implementation.md`, the existing rules for the same region in the V2 prototype, and the matching flow files and Agent Note. Later Session-layout deviations rooted in the V2 prototype follow this milestone.

## Acceptance

At 1500×837 with a synthetic Session of 1 turn / 1 message / 0 tools / 0 sub-agents / 1 case: no window-level scrollbar; the bottom edges of `.session-browser`, `.sidebar`, and `.overview` match the viewport; after scrolling the right column to the bottom, the last content sits no more than 24px above the viewport bottom; at 1500×1100 the problem list fills the remaining height with the same 24px spacing; the 390×844 mobile single-column layout and the flow loading / failure / absent states do not regress; no API contract, Session data, or problem-card content structure changes; the PR description carries the production Before capture, the fixed After capture, and the same-region V2 prototype reference.

## Non-goals

Do not change Session list / overview data semantics or query parameters; do not stretch or reflow problem-card bodies just to fill space; do not disable global `body` scrolling in a way that affects overview or evolution pages that need document scrolling; do not commit production Session content or screenshots to the repository.
