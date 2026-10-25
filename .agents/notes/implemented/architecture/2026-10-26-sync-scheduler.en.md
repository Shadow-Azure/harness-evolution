# Agent Note: Sync scheduling and single-flight locking

Status: implemented

English | [中文](2026-10-26-sync-scheduler.md)

## Problem

The scheduler and an admin manual trigger can discover pending payloads at the same time. Creating a job before acquiring its lock, or relying only on an in-memory lock, can leave orphan jobs, duplicate replays, or a permanently stuck sync state after concurrency or crashes.

## Decision

`sync_lock` is the cross-process source of truth with fixed `name=sync` and a 30-minute default TTL; an in-process `asyncio.Lock` is only the V1 fast guard. The sync job and lock row are created in one transaction, and any primary-key conflict rolls back both. An active job is reused even after its TTL, while a lock is reclaimed only when its job is missing or terminal.

The scheduler and manual API share one coordinator. By default it checks pending work every 60 seconds, and `0` disables automatic ticks. Empty pending work creates no job; a manual request returns explicit `200 idle` without inventing a jobId. A normal sync run id reuses the job id, so `ref_id` preserves both job provenance and batch association. On restart, the old audit is retained and marked interrupted, while the replacement job receives a fresh replay run id. Startup recovery adopts the sync lock before dispatching queued replacements, eliminating an unlocked execution window. Progress stays in `job_runs.progress` rather than SSE. After completed, failed, or interrupted job state is durable, the JobRunner terminal hook first terminalizes any still-running matching sync run to the same abnormal state and then releases the matching lock. Scheduler diagnostics retain only the exception type and stable code, never the exception text.

The status API reads pending, processed, active job, and its associated replay batch in one database snapshot; an active job never borrows counters from another batch. Persisted issues are remapped to fixed copy by closed-set code at the outbound boundary, and unknown codes never return free text. The light prototype top bar shows only real pending and latest-batch information. Only the admin menu exposes immediate processing. The action polls the durable job and invalidates session queries at a terminal state; failed/interrupted states show fixed user-facing copy and never echo free-form job text. Missing status hides the summary instead of showing fabricated counts.

## Alternatives considered

- An in-memory lock alone loses coordination after crashes and across future instances; rejected.
- Creating a job before acquiring its lock opens an unlocked execution window; rejected.
- Separate scheduler and manual trigger implementations allow their concurrency rules to diverge; rejected.
- SSE for sync progress contradicts the design's REST polling boundary; rejected.

## Consequences

Single-instance execution still relies on the in-process JobRunner. Multi-instance workers need `SKIP LOCKED` or an external executor over the same `sync_lock`/`job_runs` contract. TTL only recovers crashed leftovers and cannot steal a still-active job. Admin triggers return the current reused job id; ordinary users can read status only. Replacement jobs after restart retain separate ids from the interrupted batch so both audit trails remain traceable.
