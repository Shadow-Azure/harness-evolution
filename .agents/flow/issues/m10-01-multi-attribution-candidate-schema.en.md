# Multi-attribution, cache, and candidate snapshot migration

English | [中文](m10-01-multi-attribution-candidate-schema.md)

```yaml flow
kind: issue
id: m10-01
milestone: m10
depends:
  - m9-01
  - m9-04
priority: P0
status: done
scope:
  - apps/api/app/db/**
  - apps/api/app/service/bad_cases/**
  - apps/api/app/service/problems/**
  - apps/api/app/service/evolution/**
  - apps/api/alembic/**
  - packages/contracts/**
  - tests/**
  - apps/api/tests/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
adr: []
github:
  number: 210
  url: https://github.com/Shadow-Azure/harness-evolution/issues/210
```

## Background

Multiple attributions, cache metadata, and explainable candidates require in-place table evolution.

## Goals

- Allow many attributions per case.
- Extend attribution cache metadata.
- Add candidate snapshots.

## Design authority

- [06 §4.2、§5.8–§5.10、§9](../../../plans/fullstack-design/06-database-design.md)：归因、缓存与候选结构。
- [15 §6.1](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：契约与迁移顺序。

## Implementation

- Remove the case uniqueness rule.
- Use a seven-part cache key.
- Persist excluded candidates.

## Implementation steps

1. Write migration tests.
2. Implement repositories.
3. Update OpenAPI and snapshots: this slice has no DTO change, so `contract:check` stays current (contract changes belong to m11-01).

## Dependencies and boundary

- Dependencies: m9-01, m9-04
- Boundary: no engine execution.

## Verification

```sh
pnpm test:db; pnpm test:db:mysql; pnpm contract:check
```

- Many-to-many links work.
- Cache upsert is atomic.
- Candidate idempotency holds.

## Acceptance

- Existing table names remain.
- Legacy rows stay readable.

## Gates and CI

- Database, contract, and flow gates.

## Non-goals

- No parallel attribution table.
- No semantic rewrite of history.
