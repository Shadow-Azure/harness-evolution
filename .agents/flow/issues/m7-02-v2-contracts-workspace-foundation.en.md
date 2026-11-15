# V2 contracts and workspace foundation migration

English | [中文](m7-02-v2-contracts-workspace-foundation.md)

```yaml flow
kind: issue
id: m7-02
milestone: m7
depends: []
priority: P0
status: in-progress
scope:
  - apps/api/app/db/**
  - apps/api/alembic/**
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/implemented/architecture/2026-11-15-v2-workspace-foundation-migration.md
github:
  number: 223
  url: https://github.com/Shadow-Azure/harness-evolution/issues/223
```

## Background

Workspace isolation and later attribution share one contract and migration foundation.

## Goals

- Add workspace and session contracts.
- Create workspace tables and add workspace_id.
- Backfill the default workspace idempotently on both databases.

## Design authority

- [05 §3.7、§4.16](../../../plans/fullstack-design/05-api-design.md)：空间 DTO 与端点。
- [06 §3.10–§3.12、§9](../../../plans/fullstack-design/06-database-design.md)：空间表与迁移。

## Implementation

- Extend users with provider mapping fields.
- Create workspace, member, and credential tables.
- Add workspace keys and indexes to business tables.

## Implementation steps

1. Write migration failures first.
2. Implement models and the first Alembic revision.
3. Regenerate contracts and snapshots.

## Dependencies and boundary

- Dependencies: none
- Boundary: foundation only; no business endpoints.

## Verification

```sh
pnpm test:db; pnpm test:db:mysql; pnpm contract:check
```

- Empty and repeated upgrades pass.
- No workspace_id remains null.
- Contracts do not drift.

## Acceptance

- Both dialects build the foundation.
- Existing rows move to the default workspace.
- Cross-workspace uniqueness is enforced.

## Gates and CI

- Database, contract, and flow gates.

## Non-goals

- No session aggregation.
- No multi-attribution migration.
