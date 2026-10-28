# Agent Note: Evolution recovery from blocked runs

Status: implemented

English | [中文](2026-10-28-evolution-recovery.md)

## Problem

Once a run entered `blocked`, no durable timer pushed it back into execution: a transient push failure left people refreshing the page, a process restart erased any in-memory intent to recover, and a dropped stream left the page unable to tell whether the blocked stage, retry count, and next attempt time it showed were still current facts. What was missing was a recovery semantic that works from database facts alone: which failures retry automatically, which wait for a person, and what the page should trust after restart or reconnect.

## Decision

`EvolutionBlockedSweeper` is a process-local lightweight loop started by the lifespan. Every 30 seconds it scans push-blocked runs whose `next_retry_at<=now` and `retry_attempts<3` and enqueues exactly one `evolution_retry` job when due. The sweep itself holds neither the JobRunner global serial lock nor a sleep inside a job handler, so waiting for a backoff never occupies the worker or blocks another run's stage. Automatic backoff covers transient push errors only: one minute after the first failure, then five and fifteen, and after the third automatic retry still fails it writes `next_retry_at=NULL` and returns control to a person. Authentication, permission, branch-protection, and non-fast-forward failures never enter the automatic ladder. Each sweep pass performs at most one push per run, so one scan cannot retry without bound.

Evaluation and patch blocks never enter automatic backoff and accept only `POST /runs/{rid}/retry`; a manual retry first resets `retry_attempts` to zero so later failures start the 1/5/15-minute ladder again. The route admits only blocked runs and answers every other state with `RUN_NOT_RETRYABLE`; when an active `evolution_retry` job already exists, it reuses that job and returns `reused=true`, so repeated clicks never stack queue entries.

`EvolutionRetryService` clears blocked state, records `run.resumed`, and then dispatches from `blocked_stage` plus durable field facts instead of blindly re-running by stage name. In the push stage it continues finalization when a final already exists, hands a completed evaluation to apply, and otherwise repushes only the persisted candidate and resubmits its evaluation. In the eval stage it clears the old external id and submits anew, leaving that previous id traceable in the event payload. In the patch stage it regenerates from `patching` rather than jumping ahead to push or eval. Automatic and manual retries share one handler; only manual retries reset the ladder, and only automatic ones require the push stage and perform one push at a time.

Process restart marks residual running jobs as interrupted and writes `run_interrupted`; it never resumes them automatically. Only a blocked run's `next_retry_at` is a durable fact that survives restart, and the sweeper picks it up again. "Continue after restart" therefore happens only on paths that the database can re-derive, so an interrupted execution chain is never quietly reattached to a half-finished git state.

The live surface uses `evolution_run_events.seq` as its cursor: the first SSE connection and every reconnect replay from after that seq before switching to live, and an expired cursor emits `reset` so the page reloads the REST snapshot. The page subscribes only while `preparing/running`, polls every five seconds while blocked, and closes the stream on completed/failed/interrupted. `run.blocked` and `run.resumed` are notifications only; the stage, attempt count, and time shown on the page still come from the REST snapshot.

## Alternatives considered

High-frequency job polling or a separate queue for backoff were rejected: the first repeatedly queues every waiting run and occupies the single worker, while the second adds another scheduler and operational surface for a 30-second lightweight scan. Keeping the retry counter in memory was rejected because a process exit loses how far the ladder had advanced and restart cannot continue the timing. Automatic evaluation retries were rejected because an evaluation failure usually means external configuration or the implementation itself is wrong; resubmitting automatically only multiplies cost and hides the cause, while an explicit retry after a human fix stays controllable. Automatically resuming interrupted jobs was rejected because the interruption point may sit in a half-written git state, and reattaching would create inexplicable branch history. A global resident SSE connection was rejected because it holds connections and authorization context for completed runs, which is wasteful on both traffic and permission surface.

## Consequences

Automatic backoff and manual retry are delivered: a transient failure lets a blocked run recover on its own, while a permanent one stops in an explainable state and waits for a person. Python `None` in a JSON column used to be written as JSON `null`, which defeated the `eval_result IS NULL` guard and left completed rounds polling in `evaluating` forever; new writes persist SQL NULL and the `0009` migration backfills historical rows during upgrade. Real patches and real evaluation remain placeholders; the recovery layer only guarantees that existing durable facts are continued correctly, and does not judge why an external system failed. The sweeper is a process-local loop, so multi-instance deployment needs single-flight and V1 assumes one process; cross-instance takeover waits for JobRunner `SKIP LOCKED` support. The placeholder loop's own decisions live in [Placeholder evaluation and automatic turn closure](2026-10-28-placeholder-evaluation-loop.en.md).
