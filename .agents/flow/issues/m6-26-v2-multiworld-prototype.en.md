# V2 multi-workspace and attribution prototype

English | [中文](m6-26-v2-multiworld-prototype.md)

```yaml flow
kind: issue
id: m6-26
milestone: m6
depends: []
priority: P1
status: done
scope:
  - plans/ui-prototype-v2/**
  - plans/fullstack-design/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 203
  url: https://github.com/Shadow-Azure/harness-evolution/issues/203
```

## Background

The V2 multi-workspace prototype established the clickable baseline for workspaces, overview, session search, evolution, and error detail. Its target state now lives in `plans/fullstack-design`, while remote issue #203 remains open.

## Goals

- Record delivery of the V2 frontend prototype.
- Bring the prototype into the M6 historical flow.
- Align GitHub with the local flow tree.

## Design authority

- [design-v2.md](../../../plans/ui-prototype-v2/design-v2.md): prototype acceptance.
- [15-v1-v2-gap-analysis.md](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md): target-state gaps.

## Implementation

- Keep the V2 HTML prototype as the clickable baseline.
- Let the design documents own the target-state contracts.
- Limit this issue to historical status closure.

## Implementation steps

1. Confirm the prototype and design documents are on main.
2. Add issue #203 to the M6 flow tree as done.
3. Synchronize GitHub status through flow sync.

## Dependencies and boundary

- Dependencies: none
- Boundary: prototype and design assets only.

## Verification

```sh
pnpm verify:flow; pnpm lint:docs
```

- Prototype files exist and flow/docs gates pass.

## Acceptance

- Issue #203 is traceable through M6.
- M7-M11 implementation issues reuse the prototype.

## Gates and CI

- Flow and documentation gates pass.

## Non-goals

- No prototype visual changes.
- No fixture data in production.
