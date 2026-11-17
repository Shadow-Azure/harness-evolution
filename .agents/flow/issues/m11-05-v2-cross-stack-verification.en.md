# V2 cross-stack fixtures, migration, and security verification

English | [中文](m11-05-v2-cross-stack-verification.md)

```yaml flow
kind: issue
id: m11-05
milestone: m11
depends:
  - m8-05
  - m10-06
  - m11-02
  - m11-04
  - m11-07
priority: P0
status: in-progress
scope:
  - tests/**
  - fixtures/**
  - reports/**
  - plans/**
  - apps/api/**
  - apps/web/**
  - scripts/run-api.mjs
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 220
  url: https://github.com/Shadow-Azure/harness-evolution/issues/220
```

## Background

V2 spans identity, workspaces, ingest, evidence, attribution, and UI.

## Goals

- Build a full V2 fixture.
- Verify both databases and replay.
- Cover skill, agent, and knowledge triggers.

## Design authority

- [15 §8–§9](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：验收重点和证据门禁。
- [02 §4–§5](../../../plans/fullstack-design/02-features.md)：V2 阶段和验收。

## Implementation

- Seed multiple spaces and derived relations.
- Add end-to-end flows, including lane DAG and structure-tree switching.
- Archive sanitized evidence.

## Implementation steps

1. List failing scenarios.
2. Implement fixtures and tests.
3. Run all gates and store reports.

## Dependencies and boundary

- Dependencies: m8-05, m10-06, m11-02, m11-04, m11-07
- Boundary: product fixes return to owning issues.

## Verification

```sh
pnpm test:all; pnpm verify:docs; pnpm verify:bundle; pnpm verify:web-style
```

- Isolation is enforced.
- Quota, cache, and matching agree.
- No console or visual regressions.

## Acceptance

- All seven V2 goals have evidence.
- Fixtures are sanitized.

## Gates and CI

- All repository gates.
- The MySQL lane runs the V2 migration acceptance case through `test:db:mysql`.

## Non-goals

- No hidden environmental failures.
- No screenshots instead of assertions.
