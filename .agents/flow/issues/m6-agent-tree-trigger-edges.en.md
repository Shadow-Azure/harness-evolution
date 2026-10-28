# Direct trigger edges in the agent execution graph

English | [中文](m6-agent-tree-trigger-edges.md)

```yaml flow
kind: issue
id: m6-08
milestone: m6
depends: []
priority: P1
status: done
scope:
  - plans/14-15-ui-prototype/**
  - plans/fullstack-design/**
  - plans/2026-10-28-pr152-review.md
  - apps/web/src/components/agent-tree/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/implemented/bug-fix/2026-10-28-agent-tree-direct-trigger-edges.md
github:
  number: 149
  url: https://github.com/Shadow-Azure/harness-evolution/issues/149
```

## Background

The Agent execution graph renders permanent stubs from every trigger pill to the Agent box edge. The stubs ignore the actual graph edges, so pills without a child Agent or problem card still show vertical lines. Real Vue Flow edges originate at the Agent box edge, and the error-detail view can hide them behind the node layer. As a result, users see a connection to the box edge rather than a connection from the trigger pill to the target.

## Goals

- Show no vertical line for a trigger pill without a real target.
- Connect child Agents, self-skill problem cards, and discovery problem cards directly from the corresponding pill anchor.
- Stack multiple problem cards for one pill upward or downward in a stable column and chain them along that column.
- Preserve the same connection semantics in the main execution flow and error details without hiding edges behind nodes.

## Design authority

- [plans/fullstack-design/03-frontend-architecture.md §8.3](../../../plans/fullstack-design/03-frontend-architecture.md#83-agent-执行流图react-flow--vue-flow-的迁移方案): Vue Flow handles and edge paths keep the prototype semantics.
- [plans/fullstack-design/08-frontend-implementation.md §3](../../../plans/fullstack-design/08-frontend-implementation.md#3-agent-执行流图componentsagent-tree): self and discovery problem cards use trigger-point anchors.
- [plans/14-15-ui-prototype/harness-evolution.html](../../../plans/14-15-ui-prototype/harness-evolution.html): trigger pills are edge sources and problem cards stack vertically.
- The linked sections and the confirmed prototype take precedence if implementation details conflict.

## Implementation

- Aggregate occupied pill handles from real Agent edges and first problem-card edges during layout.
- Create handles only for occupied directions and position them at the pill's upper or lower boundary.
- Remove permanent stubs and raise the edge layer above Agent node backgrounds.
- Center problem cards on the pill's x coordinate; chain later cards from the previous card in the same upward or downward column.

## Implementation steps

1. Cover disconnected pills, connection aggregation, and vertical problem-card stacking in layout tests.
2. Cover on-demand handles, pill anchors, and problem-card stack handles in node tests.
3. Extend layout and node types to emit trigger connection state and stacked problem-card edges.
4. Adjust the AgentTree canvas layer and run frontend, flow, and documentation gates.

## Dependencies and boundary

- 依赖：无
- Delivery boundary: change only Agent graph anchors, edges, and stacking. Do not change collapse logic, problem-card interaction, data contracts, or backend behavior.

## Verification

```sh
pnpm --filter @harness/web exec vitest run src/components/agent-tree/layout.test.ts src/components/agent-tree/nodes/AgentNode.test.ts src/components/agent-tree/nodes/BadCaseNode.test.ts
pnpm typecheck:web
pnpm lint:web
```

- Unit tests assert that disconnected pills create no handles, real connections create pill-anchored handles, and upward/downward problem cards chain correctly; all assertions pass.
- Type checking and lint pass without errors.

## Acceptance

- `/agent-tree-demo?variant=large` shows a line only for pills with a child Agent or problem card.
- Child-Agent edges start at the pill's lower boundary; an upper error card connects from its lower edge to the pill's upper edge; a lower error card connects from the pill to the first card.
- Multiple problem cards for one pill form a line upward or downward and chain from the preceding card.
- All edges remain visible in execution details without blocking text, clicks, or zoom controls.

## Gates and CI

- `pnpm test:web`
- `pnpm typecheck:web`
- `pnpm lint:web`
- `pnpm verify:flow`
- `pnpm lint:docs` / `pnpm verify:docs`
- `pnpm verify:web-style`

## Non-goals

- Do not change the React Flow to Vue Flow layout architecture or collapse thresholds.
- Do not change left/right problem-card selection, card content, or deep-link behavior.
- Do not change APIs, databases, or shared contracts.
