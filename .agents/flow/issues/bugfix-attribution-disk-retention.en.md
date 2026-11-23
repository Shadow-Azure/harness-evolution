# Cap on-disk attribution records via .env and evict the oldest first

English | [中文](bugfix-attribution-disk-retention.md)

```yaml flow
kind: issue
id: bugfix-28
milestone: bugfix
depends: []
priority: P1
status: backlog
scope:
  - apps/api/**
  - attribute/README*
  - deploy/env.production.example
  - .agents/flow/issues/bugfix-attribution-disk-retention*
  - .agents/notes/**
adr: []
github:
  number: 532
  url: https://github.com/Shadow-Azure/harness-evolution/issues/532
```

## Background

Target binding and uncached wizard runs write per-case inputs, execution logs and report copies under `attribute/<workspace>/`. Multiple batches can share session evidence, target definitions and Skill snapshots. Disk usage keeps growing even when later runs reuse database reports. Related issues are #387 and #417.

## Goals

Expose a per-workspace record limit in the deployment `.env`. When the limit is exceeded, automatically evict the earliest completed records first and keep more recent records available.

## Design authority

Preserve the database semantics of reports and candidates and the input archive used by binding batches and wizard runs. [Backend design §5.13, attribution and caching](../../../plans/fullstack-design/07-backend-implementation.md#513-归因生成与缓存serviceevolutionattributionpy)

## Implementation

- Suggested setting name is `HE_ATTRIBUTION_CACHE_MAX_RECORDS`. Provide a documented, finite positive default and a deployment override. Reject zero, negative or invalid values at startup.
- Count one on-disk record per `(batch_id, badcase_id)` in each workspace. Retrying a case reuses its record, a fresh Run counts separately, and a database-only cache hit adds zero. Order by persistent completion time with a stable identifier as tie-breaker.
- Check after a batch completes and reconcile existing archives on restart. Evict only the excess records. Remove each eligible case’s archived inputs, logs and report copy together. Protect queued and running cases and the inputs needed for retry. If protected records prevent convergence, record the reason and retry on a later check.
- Collect shared evidence, definitions and Skill snapshots after their last live reference in the workspace is released. Preserve current bindings, uploaded packages, the bundled default, database reports, candidate links and wizard cache reuse. Historical lookups can distinguish an evicted disk archive.

## Implementation steps

Define the count, completion timestamp and live references. Coordinate cleanup and publication per workspace, report counts before and after the sweep, and record evictions and skip reasons. Support restart after partial cleanup and document the setting in the attribution directory guide and deployment example.

## Dependencies and boundary

Cover the common archive path for SQLite and production MySQL. Restrict collection to its workspace and support concurrent binding attribution, wizard recomputation and cached reads.

## Verification

Add synthetic tests and run `pnpm test:api -- tests/attribution -k retention`. Set the cap to 3 and create 5 records with distinct completion times. Have the oldest and newest reference the same evidence and use a second workspace as a control.

## Acceptance

1. With a cap of 3, adding the fourth record evicts only the oldest. With five present, retain the latest three. Lowering the cap to 2 and restarting evicts one more.
2. Count each workspace independently. Retries and cache hits follow the counting rules. Active work keeps its frozen inputs and the count converges after protection ends.
3. Evicted records’ database reports remain readable and reusable. Retained shared evidence verifies. Concurrent publication and an interrupted sweep preserve other workspaces, current bindings, uploaded packages and files needed for retained records.

## Gates and CI

Include threshold, ordering, shared-reference and recovery cases in API CI. Run `pnpm lint:api`, `pnpm typecheck:api` and the relevant SQLite and MySQL tests.

## Non-goals

Database report deletion, replacing the count limit with a time-to-live and a new administrative UI fall outside this issue.
