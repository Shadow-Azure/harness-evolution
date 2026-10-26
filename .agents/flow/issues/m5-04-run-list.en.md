# m5-04 Run List

English | [中文](m5-04-run-list.md)

```yaml flow
kind: issue
id: m5-04
milestone: m5
depends:
  - m5-01
priority: P0
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - tests/**
  - plans/**
  - reports/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 53
  url: https://github.com/Shadow-Azure/harness-evolution/issues/53
```

## Background

M5-04 is an independently mergeable vertical slice. Implementation decisions must follow the linked fullstack-design sections and must not create a second design authority inside the Issue.

## Goals

- Deliver the boundary declared by M5-04 and make it independently verifiable with the commands below.
- Keep contracts, the database, the frontend and existing gates aligned.
- Give failures, empty states and duplicate input explicit behavior.

## Design authority

- [05 §3.5/§4.10 运行模型](../../../plans/fullstack-design/05-api-design.md)
- [08 §8 列表](../../../plans/fullstack-design/08-frontend-implementation.md)
- [02 F10](../../../plans/fullstack-design/02-features.md)

## Implementation

- Implement the running/history API and list UI with stage, progress, status, creator and time; place the creator in the prototype's upper-right metadata slot without adding a visual row.
- Support refresh and empty states.

## Implementation steps

1. Write failing tests for status grouping and backend-owned copy.
2. Implement the API and page.
3. Drive E2E from fixtures.

## Dependencies and boundary

- Depends on: m5-01.
- Delivery boundary: implement only this Issue's capability; adjacent behavior outside acceptance belongs to dependencies or later Issues.

## Verification

```sh
pnpm test:api -- tests/m5-04-run-list
pnpm test:db
pnpm test:web
pnpm test:e2e
pnpm contract:check
```

- List tests pass.
- Running/history order and progress come from the backend.

## Acceptance

- The frontend does not derive state.

## Gates and CI

- Route gate, component tests and E2E.

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
