# m4-03 Problem Cards

English | [中文](m4-03-problem-cards.md)

```yaml flow
kind: issue
id: m4-03
milestone: m4
depends:
  - m4-02
priority: P0
status: in-progress
scope:
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - tests/e2e/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 48
  url: https://github.com/Shadow-Azure/harness-evolution/issues/48
```

## Background





m4-03 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m4-03 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [03 §8.3 问题卡](../../../plans/fullstack-design/03-frontend-architecture.md)
- [08 §3.4 联动](../../../plans/fullstack-design/08-frontend-implementation.md)
- [09 追溯矩阵](../../../plans/fullstack-design/README.md)

## Implementation





- Read five-state problem details and render cards against `anchor.agentId + anchor.eventIndex` in the execution-flow graph.
- Use side, trigger, discovery, and fallback connector semantics for `self + agent`, `self + skill`, `discovery`, and `eventIndex=-1`; an invalid host keeps the card visible without creating an orphan edge.
- Stack cards sharing an anchor deterministically by `badCaseId`; list the real ID, five-state attribution, summary, reporter, and metadata facts.
- Share one active `badCaseId` between list and canvas for two-way location and highlighting; scroll the list after canvas location and cancel late initial-scroll resets.
- Keep problem loading, failure, retry, and empty states independent from summary and tree loading.

## Implementation steps





1. Write failing tests for five-state cards, anchors, malformed anchors, and two-way selection.
2. Implement problem cards, semantic connectors, the five-state list, and the independent query.
3. Cover all five states, desktop/mobile layout, and location recovery with four real fixture Sessions.

## Dependencies and boundary





- 依赖：m4-02
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:web
pnpm test:e2e -- "m4 problem cards"
pnpm typecheck:web
pnpm lint:web
```

- Four fixture Sessions collectively show unanalyzed, non-issue, model, prompt, and error states.
- Clicking a list row locates and highlights its canvas card; clicking a canvas card scrolls and highlights its list row.
- The 1408px and 390px layouts have no horizontal overflow and the browser console is clean.

## Acceptance





- 问题可视化可回链 badCaseId

## Gates and CI





- Component tests, pure layout tests, real Chrome E2E, TypeScript, ESLint, token color source, and bundle boundaries.

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
- Do not implement the m4-04 error-detail page or attribution tabs.
