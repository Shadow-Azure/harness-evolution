# Session parent-child reconciliation and unresolved branches

English | [中文](m9-03-session-relation-reconciliation.md)

```yaml flow
kind: issue
id: m9-03
milestone: m9
depends:
  - m9-01
  - m9-02
priority: P0
status: backlog
scope:
  - apps/api/app/service/acquisition/agent_tree.py
  - apps/api/app/service/acquisition/**
  - apps/api/app/api/sessions.py
  - apps/web/src/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 238
  url: https://github.com/Shadow-Azure/harness-evolution/issues/238
```

## Background

A matching parent toolUseId and child metadata can coexist with a missing tool result, producing inconsistent linked state.

## Goals

- Emit four relation confidence levels.
- Keep derived children visible.
- Preserve unresolved diagnostics.

## Design authority

- [15 §9.1](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：父子关系证据。
- [06 §3.3–§3.4](../../../plans/fullstack-design/06-database-design.md)：agents 与 agent_events。

## Implementation

- Use one reconciliation algorithm.
- Downgrade confidence instead of dropping nodes.
- Expose evidence in APIs and UI.

## Implementation steps

1. Write three tree fixtures.
2. Implement confidence and ordering.
3. Add evidence labels.

## Dependencies and boundary

- Dependencies: m9-01, m9-02
- Boundary: no potential matching.

## Verification

```sh
pnpm test:api -- tests/acquisition tests/sessions; pnpm test:web
```

- All four children link.
- The final review is derived.
- Unknown parents remain unresolved.

## Acceptance

- Exports and internal assembly agree.
- Unresolved nodes remain visible.

## Gates and CI

- API, Web, fixture, and flow gates.

## Non-goals

- No time-based guessing.
- No hidden orphan nodes.
