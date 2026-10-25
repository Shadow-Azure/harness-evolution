# m2-07 Sync Scheduler

English | [中文](m2-07-sync-scheduler.md)

```yaml flow
kind: issue
id: m2-07
milestone: m2
depends:
  - m2-06
priority: P0
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - fixtures/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - reports/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 39
  url: https://github.com/Shadow-Azure/harness-evolution/issues/39
```

## Background

Local payload import and idempotent replay exist, but the service cannot yet discover pending data periodically, trigger a sync manually, or serialize all trigger sources.

## Goals





- Process pending payloads by default every 60 seconds; when configured as `0`, only admins may trigger manually.
- Let the scheduler and manual callers share the durable `sync_lock`, in-process guard, and serial JobRunner.
- Show real pending state in the top bar and let admins process immediately; sync never uses SSE.

## Design authority





- [01 §4.3.4 Background scheduling](../../../plans/fullstack-design/01-architecture.md)
- [04 §7 Jobs](../../../plans/fullstack-design/04-backend-architecture.md)
- [06 §3.7 sync_lock](../../../plans/fullstack-design/06-database-design.md)

## Implementation

- `sync_lock` has a 30-minute TTL. An active job is reused even after the TTL, while terminal or missing jobs may be reclaimed.
- Job and lock rows are created in one transaction. The handler runs through the serial JobRunner, and a terminal hook releases only the matching jobId.
- `GET /api/acquisition/status` returns activeJobId, pending/processed counts, the latest batch, last/next run times, and sanitized errors.
- `POST /api/acquisition/sync` is admin-only. With no pending work it returns `200 {jobId:null,status:"idle",reused:false}`.
- The light prototype top bar shows a quiet pending summary. The admin menu offers immediate processing, polls the job, and invalidates session queries.

## Implementation steps





1. Write failing tests for concurrency, TTL, error/cancellation release, no-pending, status, and the top bar.
2. Add the `sync_lock` migration, repository, shared coordinator, and scheduler lifespan.
3. Register the sync handler, generate contracts, and integrate the light top bar.

## Dependencies and boundary





- 依赖：m2-06
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m2-07-sync-scheduler
pnpm test:db
pnpm test:web -- TopNav
pnpm test:e2e -- m1-shell
```

- Concurrent scheduler/manual callers create exactly one job; the loser reuses the same jobId.
- Success, failure, and cancellation release the matching lock; stale terminal or missing jobs are recoverable.
- No pending work creates no job; manual returns explicit idle.
- At 390px the auxiliary pending status is hidden while the user menu and logout remain available.

## Acceptance





- Sync is recoverable and observable.
- Manual sync is admin-only.
- Missing status or a narrow viewport cannot break the shell or show fabricated counts.

## Gates and CI





- Concurrency tests, dual-dialect schema, contract generation, and real-Chrome top-bar E2E.

## Non-goals

- Upstream pull is not implemented here.
