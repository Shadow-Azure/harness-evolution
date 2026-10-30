# Scheduled trajectory sync for bad-case root sessions

English | [涓枃](m6-bad-case-session-sync.md)

```yaml flow
kind: issue
id: m6-15
milestone: m6
depends:
  - m2-07
  - m4-01
priority: P1
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - fixtures/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
  - reports/**
  - docs/**
adr: []
github:
  number: 173
  url: https://github.com/Shadow-Azure/harness-evolution/issues/173
```

## Background

`bad_cases.bad_case_session_id` already points at the root session a problem belongs to, but this service does not guarantee that the root session's raw trajectory has entered `trajectory_payloads`. Trajectory ingestion currently has only two paths: development-only local directory import, and the administrator-triggered `POST /api/acquisition/pull`; both require an operator who knows the session ids or the window. As bad_cases keeps growing, problem detail, the execution-flow graph, and evolution launch can all miss the session because its payload is absent.

The existing upstream trajectory contract (`third_party_api/trajectory`) returns a whole root package in one call. The query service integrated here is different: API 1 returns only the direct child sessionIds triggered by one session (main agent or subagent), so the tree must be expanded level by level; API 2 returns one agent's trajectory and forbids concurrent calls. The existing pull's "one package per root" model therefore does not fit, and a new client plus scheduling path is required.

## Goals

- Add a scheduled job that reads distinct root session ids from `bad_cases`, selects the unsynced roots, and fills the raw trajectories of the main agent and every subagent into `trajectory_payloads`.
- Reuse the existing normalization/replay pipeline after payloads are written so the session, Agent tree, and problem read models become queryable immediately.
- Add a root-session sync status table recording each root's state, attempts, last error, agent count, and completion time, supporting idempotent reruns and failure retries.
- Add a read-only statistics API plus shared contract: total root sessions involved in bad_cases, synced count, and unsynced count.
- Show those counts in the frontend, distinguishing unsynced, syncing, and failed.
- Make the scheduled job single-flight; while the previous run is unfinished, the next trigger must not process the same batch again, with the exact skip/queue/merge policy settled in the design document.

## Design authority

- [04 搂5 data seams](../../../plans/fullstack-design/04-backend-architecture.md#L204-L214): boundaries for raw trajectories, external tables, and fixtures.
- [05 搂4.8 raw trajectory ingestion](../../../plans/fullstack-design/05-api-design.md#L688-L708): existing acquisition endpoints and job semantics.
- [06 搂3.0 trajectory_payloads](../../../plans/fullstack-design/06-database-design.md#L105-L145): the single raw payload store and pending detection.
- [02 F9 trajectory ingestion and normalization](../../../plans/fullstack-design/02-features.md): capability boundary and demo-data rules.
- [11 Scheduled sync for bad-case root sessions](../../../plans/fullstack-design/11-bad-case-session-sync.md): status table, query-service adapter, traversal, overlap policy, and frontend statistics.
- Chapter 11 wins on conflict.

## Implementation

- Add a query-service client for API 1 (direct child session ids) and API 2 (single-agent trajectory), with strict response models, timeouts, retries, and error mapping; API 2 calls stay serial within the process.
- Add a root-session backfill service that expands recursively from each bad_cases root (main agent 鈫?direct children 鈫?grandchildren), deduplicating and guarding against cycles; each agent's trajectory is written to `trajectory_payloads` under the existing `(root_session_id, agent_id)` one-row-per-agent model.
- Add scheduling and a job kind that reuse the existing scheduler and `JobRunner` patterns, with single-flight and overlap handling; batch size, retry ladder, and state transitions are settled in the design document.
- Add a status table and alembic migration with at least root_session_id, state, attempts, last error, agent count, synced time, and updated time, with root_session_id unique.
- Add the statistics API and shared contract for total, synced, and unsynced counts; the frontend renders loading, empty, and failure states.
- Add tests for multi-level traversal, duplicates and cycles, the serial API 2 constraint, single-flight and overlap, failure isolation, status idempotency, and the statistics API plus frontend rendering.

## Implementation steps

1. Produce the design document and prototype changes, settle the status table, API contract, overlap policy, and frontend placement, and get screenshot confirmation.
2. Contract and models: query-service response models, statistics DTOs, OpenAPI and generated types.
3. Database: status table model and alembic migration, verified on SQLite and MySQL.
4. Client and traversal: recursive API 1 expansion, serial API 2 fetches, payload writes, and shared replay.
5. Scheduling and single-flight: job kind, periodic trigger, overlap handling, failure retries, and status updates.
6. API and frontend: statistics endpoint, page rendering, loading/empty/failure states, and refresh.
7. Tests and gates; finish local smoke testing against a mock query service.

## Dependencies and boundary

- Dependencies: m2-07 (scheduling and job infrastructure), m4-01 (external problem read models).
- Boundary: only backfill bad_cases root-session trajectories plus status/statistics; bad_cases stays "externally written, same database, read-only here"; the existing manual pull contract and semantics stay unchanged; CI never calls the real query service.

## Verification

```sh
pnpm test:api -- tests/m6-15-bad-case-session-sync
pnpm test:db
pnpm test:web
pnpm test:e2e -- "m6 bad case sync"
pnpm verify:flow
pnpm lint:docs
```

- Under a mock query service, N root sessions produce complete main/subagent payloads and correct status counts.
- Retriggering while the previous job is unfinished produces no concurrent batch.
- API 2 call sequences never overlap.
- Frontend counts match the backend.

## Acceptance

- Every unsynced root session in bad_cases eventually has complete main + subagent payloads and normalizes into a visible Session/Agent tree.
- The status table is idempotent per root session; failures are retryable and their errors are visible.
- The scheduled job is single-flight and does not refetch the same batch while a run is active.
- API 2 is strictly serial.
- The frontend shows total, synced, and unsynced counts matching the backend after refresh.
- All related gates pass.

## Gates and CI

- `pnpm test:api` / `pnpm test:db[:mysql]` / `pnpm test` / `pnpm typecheck:api`
- `pnpm test:web` / `pnpm typecheck:web` / `pnpm lint:web`
- `pnpm test:e2e`
- `pnpm contract:check` / `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`

## Non-goals

- Do not change the direct-database bad_cases read boundary or its external writer.
- Do not replace or remove the existing administrator-triggered pull; this issue only adds an automatic backfill path.
- Do not call the real query service from CI; real integration stays in local mock and smoke testing.
- Do not detect trajectory content changes or rebuild everything; whether incremental refetch is included is settled by the design document.

