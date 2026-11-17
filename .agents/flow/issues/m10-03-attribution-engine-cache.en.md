# Object attribution engine, cache, and candidate persistence

English | [中文](m10-03-attribution-engine-cache.md)

```yaml flow
kind: issue
id: m10-03
milestone: m10
depends:
  - m10-01
  - m10-02
priority: P0
status: done
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/service/jobs.py
  - apps/api/app/config.py
  - apps/api/app/main.py
  - apps/api/app/db/**
  - apps/api/alembic/**
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
adr: []
github:
  number: 212
  url: https://github.com/Shadow-Azure/harness-evolution/issues/212
```

## Background

Potential cases need revision-scoped reusable attribution.

## Goals

- Add the engine protocol.
- Implement cache and reuse accounting.
- Persist candidates and links atomically.

## Design authority

- [07 §5.13](../../../plans/fullstack-design/07-backend-implementation.md)：归因生成与缓存。
- [06 §4.2、§5.8](../../../plans/fullstack-design/06-database-design.md)：缓存语义。

## Implementation

- Keep engines pure.
- Persist non_target evidence.
- Use knowledge evidence in reasoning.

## Implementation steps

1. Write cache tests.
2. Implement runner and registry.
3. Add retry behavior.

## Dependencies and boundary

- Dependencies: m10-01, m10-02
- Boundary: no real LLM ranking.

## Verification

```sh
pnpm test:api -- tests/attribution; pnpm test:db; pnpm test:db:mysql
```

- Reuse counts are exact.
- Cache-off rewrites.
- Non-target stays out of clusters.

## Acceptance

- Results are revision-scoped.
- Failures are recoverable.

## Gates and CI

- API, database, contract, and flow gates.

## Non-goals

- No bad-case mutation.
- No claim of final model quality.
