# Workspace bad-case ingest, quota, and idempotency

English | [中文](m8-01-workspace-bad-case-ingest.md)

```yaml flow
kind: issue
id: m8-01
milestone: m8
depends:
  - m7-05
  - m7-06
priority: P0
status: in-progress
scope:
  - apps/api/app/api/ingest.py
  - apps/api/app/service/workspaces/**
  - apps/api/app/db/crud/**
  - apps/api/app/middleware/**
  - apps/api/app/errors.py
  - apps/api/app/main.py
  - apps/api/tests/**
  - packages/contracts/**
  - docs/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 231
  url: https://github.com/Shadow-Azure/harness-evolution/issues/231
```

## Background

Each workspace needs a stable machine ingest endpoint with transactional quota and idempotency.

## Goals

- Authenticate workspace credentials.
- Upsert duplicates without quota growth.
- Reject quota overflow without data loss.

## Design authority

- [05 §3.8、§4.17](../../../plans/fullstack-design/05-api-design.md)：上报 DTO 与端点。
- [06 §4.1](../../../plans/fullstack-design/06-database-design.md)：bad_cases 归属与索引。

## Implementation

- Ignore body workspace identity.
- Lock and count inside the transaction.
- Mark the root session for sync.

## Implementation steps

1. Write concurrency tests.
2. Implement ingest and sync marking.
3. Update the contract.

## Dependencies and boundary

- Dependencies: m7-05, m7-06
- Boundary: no ingest UI.

## Verification

```sh
pnpm test:api -- tests/ingest; pnpm test:db; pnpm test:db:mysql
```

- Quota boundaries are exact.
- Duplicates preserve usage.
- Cross-workspace IDs fail.

## Acceptance

- Credentials only ingest.
- No quota oversell.

## Gates and CI

- API, database, contract, and flow gates.

## Non-goals

- No registration.
- No body-selected workspace.
