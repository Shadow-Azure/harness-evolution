# Seven-step prepare, cluster input, and legacy run adaptation

English | [中文](m10-04-seven-step-prepare.md)

```yaml flow
kind: issue
id: m10-04
milestone: m10
depends:
  - m10-03
priority: P0
status: in-progress
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/service/jobs.py
  - apps/api/app/db/**
  - apps/api/app/api/**
  - apps/api/app/main.py
  - apps/api/tests/**
  - packages/contracts/**
  - apps/web/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 213
  url: https://github.com/Shadow-Azure/harness-evolution/issues/213
```

## Background

New runs flow from workspace cases through linking, potential, attribution, and clustering.

## Goals

- Implement units zero through six.
- Cluster attributed candidates only.
- Adapt legacy runs to seven steps.

## Design authority

- [07 §5.11](../../../plans/fullstack-design/07-backend-implementation.md)：七步 prepare。
- [05 §3.6](../../../plans/fullstack-design/05-api-design.md)：七步产出。

## Implementation

- Make candidates idempotent.
- Retry attribution blockers.
- Share step builders.

## Implementation steps

1. Write state tests.
2. Replace prepare.
3. Test legacy adaptation.

## Dependencies and boundary

- Dependencies: m10-03
- Boundary: no real patch/eval replacement.

## Verification

```sh
pnpm test:api -- tests/evolution; pnpm contract:check
```

- Units advance correctly.
- Repeated prepare is idempotent.
- Legacy keys match.

## Acceptance

- Seven-step runs recover.
- Cluster-only stops at clustering.

## Gates and CI

- API, state, contract, and flow gates.

## Non-goals

- No fabricated evaluation.
- No legacy deletion.
