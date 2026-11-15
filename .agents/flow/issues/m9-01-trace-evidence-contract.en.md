# Trace evidence contracts, relation confidence, and completion migration

English | [中文](m9-01-trace-evidence-contract.md)

```yaml flow
kind: issue
id: m9-01
milestone: m9
depends:
  - m7-02
priority: P0
status: backlog
scope:
  - apps/api/app/db/**
  - apps/api/alembic/**
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 236
  url: https://github.com/Shadow-Azure/harness-evolution/issues/236
```

## Background

Current tree state cannot express open tool calls, missing child reports, or external attempt failures.

## Goals

- Add execution and relation fields.
- Add revision and model evidence.
- Keep runtime and parser versions separate.

## Design authority

- [15 §9.1–§9.4](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：真实会话证据门禁。
- [06 §3.3–§3.4、§9](../../../plans/fullstack-design/06-database-design.md)：轨迹表演进。

## Implementation

- Extend agent tables.
- Split parse health from execution outcome.
- Add closed API enums.

## Implementation steps

1. Write migration tests.
2. Implement columns and indexes.
3. Update contracts.

## Dependencies and boundary

- Dependencies: m7-02
- Boundary: schema only.

## Verification

```sh
pnpm test:db; pnpm test:db:mysql; pnpm contract:check
```

- Legacy rows backfill safely.
- Both dialects upgrade twice.
- Contracts compile.

## Acceptance

- Evidence can represent incomplete workflows.
- States remain closed.

## Gates and CI

- Database, contract, and flow gates.

## Non-goals

- No revision inference.
- No attribution schema.
