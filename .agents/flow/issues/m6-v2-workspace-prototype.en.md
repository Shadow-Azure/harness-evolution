# V2 workspace and attribution flow frontend prototype

English | [中文](m6-v2-workspace-prototype.md)

```yaml flow
kind: issue
id: m6-24
milestone: m6
depends: []
priority: P1
status: in-progress
scope:
  - plans/v2-ui-prototype/**
  - .agents/notes/**
  - .agents/flow/**
adr: []
github:
  number: 203
  url: https://github.com/Shadow-Azure/harness-evolution/issues/203
```

## Background

The frontend already provides login, Session browsing, error details, a single attribution view, and the evolution launch wizard. Domain data has no workspace context, and attribution currently precedes launch, so one bad case cannot be expressed as a potential case for multiple target versions. V2 needs a clickable prototype to validate navigation, permission entry points, ingestion setup, overview drill-down, and multi-attribution interactions before production changes begin.

## Goals

- Deliver a clickable V2 prototype covering global admin, workspace admin, member, and viewer boundaries.
- Cover workspace quotas, ingestion, overview aggregation and paginated drill-down, the latest 10 Sessions with exact search, multi-attribution error details, and potential bad case filtering with cache selection.
- Define migration that reuses the Vue pages, authentication state, and deep links.

## Design basis

- [02-features.md §2.1](../../../plans/fullstack-design/02-features.md): preserve the core responsibilities of Session lists, execution flow, bad cases, and error details.
- [02-features.md §2.2](../../../plans/fullstack-design/02-features.md): preserve target, version, and time window launch conditions while expanding hit preview into associated Sessions and potential bad cases.
- [03-frontend-architecture.md §4](../../../plans/fullstack-design/03-frontend-architecture.md): retain the one-way route page, shared component, composable, and API dependencies.
- [V2 prototype design](../../../plans/v2-ui-prototype/design.md): define workspace context, multiple attributions, and migration within those boundaries.

## Implementation

- Add a standalone static HTML prototype without changing production Vue pages or APIs.
- Document page states, permission matrices, compatible routes, and data-contract migration recommendations.
- Add an Agent Note for workspace context and moving attribution into the evolution flow.

## Steps

1. Audit the existing prototype, Vue pages, authentication boundary, and bad case/evolution relationships.
2. Write the V2 navigation and migration design and build the clickable static prototype.
3. Check key interactions and desktop/narrow layouts in a browser, then run flow and documentation gates.

## Dependencies and delivery boundary

- Dependencies: existing light visual tokens, authentication, Session error details, and evolution wizard.
- Non-goals: no production API, schema migration, real Cookie authentication change, or frontend business logic.

## Independent verification

```sh
node plans/v2-ui-prototype/verify.mjs
```

- All prototype structure and key interaction assertions pass.

```sh
pnpm verify:flow; pnpm lint:docs
```

- Flow, bilingual pairing, Agent Note, and documentation gates pass.

## Acceptance

- Overview filters and paginates bad cases and opens the selected case's problem tab in its Session error detail.
- Sessions default to 10 items and exact search runs on Enter; each bad case expands to multiple paginated attributions.
- The wizard includes target/version/window, Session association, trigger-point potential-case policy, custom policy, and a cache switch.
- Workspace creation, quota changes, member roles, and ingestion have explicit entry points; public registration remains absent.
- The design documents legacy route compatibility, component reuse, and staged migration boundaries.

## Gates and CI

- `node plans/v2-ui-prototype/verify.mjs`: static structure assertions.
- `pnpm verify:flow`: issue trio, scope, and state machine.
- `pnpm lint:docs`: bilingual pairing, links, and formatting for the new Agent Note and flow documents.

## Non-goals

- Do not change `apps/`, `packages/contracts`, or production tests in this issue.
- Do not implement real ingestion, authorization, aggregate queries, or attribution caching.
