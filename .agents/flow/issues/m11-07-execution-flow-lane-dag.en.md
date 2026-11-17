# Execution-flow lane DAG with structure-tree fallback

English | [中文](m11-07-execution-flow-lane-dag.md)

```yaml flow
kind: issue
id: m11-07
milestone: m11
depends:
  - m8-05
  - m9-04
priority: P1
status: ready
scope:
  - apps/web/src/components/agent-tree/**
  - apps/web/src/components.d.ts
  - apps/web/src/pages/agent-tree-demo/**
  - apps/web/src/pages/sessions/**
  - apps/web/src/pages/errors/**
  - tests/e2e/**
  - plans/fullstack-design/**
  - plans/ui-prototype-v2/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 276
  url: https://github.com/Shadow-Azure/harness-evolution/issues/276
```

## Background

The V2 prototype makes the default execution flow for Session and error detail a small-window lane DAG: one lane represents one agent invocation, a bar's left/right edges map to a log-line interval, cross-lane overlap means concurrency, nesting uses `A1/A1.1` depth, and selecting a bad case keeps all concurrent branches while highlighting the matching BC. The prototype still keeps the structure tree as a toggled view.

However, 02/03/08/09 still describe a Vue Flow node tree, `×N` message gaps, folding when there are more than 8 subagents, and filtering the panel down to the selected finding card. M11-02 explicitly declares "do not change execution-flow layout", so no M7–M12 issue owns the target state.

## Goals

- Render the small-window lane DAG by default with `A1/A1.1` depth, log-line interval bars, cross-lane concurrency, and BC markers.
- Keep all lanes expanded and use viewport zoom/pan instead of `>8` folding.
- Keep the structure tree as a toggled view; both views share the selected case and deep link.
- Keep all concurrent branches when a bad case is selected; highlight only its BC and lead line instead of filtering other branches.
- Remove the leftover timeline entry and `Open timeline` CTA from the V2 execution flow.

## Design authority

- [02 §2.1 Session error view](../../../plans/fullstack-design/02-features.md#21-session-错误查看域): execution-flow and error-detail behavior.
- [08 §3 Agent execution flow](../../../plans/fullstack-design/08-frontend-implementation.md#3-agent-执行流图componentsagent-tree): lane DAG, structure tree, and selected state.
- [09 §1.2 Session error view](../../../plans/fullstack-design/09-review-guide.md#12-session-错误查看): review checklist.
- [design-v2 §8 Error detail](../../../plans/ui-prototype-v2/design-v2.md#8-错误详情一个-bad-case--多条归因): prototype interaction.

## Implementation

- Add a `LaneDag` view: virtual canvas, fixed-height viewport, wheel zoom, drag pan, fit/1:1, and touch pan.
- Express depth with `A1/A1.1` paths and indentation, concurrency with cross-lane horizontal overlap, and keep bars in the same lane non-overlapping.
- Keep main-chain `×N no-trigger` bars in log-line intervals; do not render `×N` message-gap nodes.
- Keep `AgentTree` as the toggled structure-tree view; DAG and tree share `badCaseId` selection and `locate`.
- When a case is selected, keep every DAG branch and highlight its BC lead line; error detail must not filter the whole flow.
- Remove the timeline tab, page, and `Open timeline` button from the V2 page; keep only Session and error-detail entries.

## Implementation steps

1. Extract a shared `laneModel` from the current structure-tree and DAG adapters; add depth/concurrency/interval unit tests.
2. Implement the small viewport and zoom/pan/fit while keeping the structure-tree toggle.
3. Wire selection, locate, and deep links in Session and error detail.
4. Remove the timeline entry/page, then update E2E and visual regression.
5. Update 02/03/08/09/15 and design-v2, including the review checklist.

## Dependencies and boundary

- Dependencies: m8-05, m9-04
- Non-goals: do not change the backend tree contract; do not implement the multi-attribution sidebar (M11-02); do not implement parser/evidence work (M9).

## Verification

```sh
pnpm test:web
pnpm typecheck:web
pnpm test:e2e -- --pattern execution-flow
pnpm verify:bundle
```

- Session and error detail render the lane DAG by default with no same-lane bar overlap.
- Cross-lane overlap is visible; selecting a case keeps all branches and highlights it.
- Switching to the structure tree preserves selection and deep link.
- A 56-subagent session can be browsed with zoom/pan and has no `>8` fold node.
- No timeline entry remains on the page.

## Acceptance

- Default view, selection, deep link, and structure-tree toggle match the V2 prototype.
- All lanes are expanded and browsed through viewport zoom/pan, not folding.
- The same case selection is consistent across DAG, structure tree, and problem list.
- No console errors, obvious clipping/overlap, or layout jumps.

## Gates and CI

- Web unit tests, types, E2E, bundle, visual regression, and flow gates.

## Non-goals

- Do not restore a React Flow/Vue Flow node tree as the default view.
- Do not keep a timeline page or `Open timeline` CTA.
- Do not express selection by filtering branches.
