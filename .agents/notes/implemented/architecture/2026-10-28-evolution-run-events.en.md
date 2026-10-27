# Agent Note: Evolution Event Replay and Execution Logs

Status: implemented

English | [中文](2026-10-28-evolution-run-events.md)

## Problem

The M1 event projection already provided SQL replay and interruption notifications, but the evolution parent relationship, resource authorization, generic failure writes, REST pagination, and run-detail log UI were still missing; `lastEventSeq` could only return a hardcoded zero, so the debugging path after refresh had no complete source of truth.

## Decision

`evolution_run_events` belongs to `evolution_runs` through a `run_id` foreign key and uses `(run_id, seq)` as its stable replay cursor. `EvolutionRunEventService` recursively redacts JSON, messages, and error details before appending, truncates `error.detail` to 8KB by UTF-8 bytes, persists the event, and then publishes a `run.event` notification; unrecoverable failures, process interruptions, retryable blocks, and resumes also synchronize run state. REST `/runs/{rid}/events` supports `afterSeq`, `limit`, and level filtering as the sole replay source after refresh and restart, while SSE only carries notifications. Run detail fills `lastEventSeq` from the real max sequence, and its log tab pages REST with filtering, collapsible errors, manual refresh, scroll pause, and step/cluster deep links.

## Alternatives considered

Keeping events only in the in-memory EventBus would lose process facts on refresh and restart; building logs directly from raw stderr would leak credentials and break payload bounds; treating SSE frames as history would depend on slow connections, queue eviction, and reconnect races. Scattering redaction across callers would let future engine events bypass the security boundary, so safety handling lives centrally in the event service.

## Consequences

Event storage follows the run lifecycle with auditability, replay, and cascade cleanup, while the UI can locate a failure directly. In one process, sequence allocation uses unique-conflict retries to avoid gaps, but it does not promise high-concurrency throughput across instances; run-state and event writes remain adjacent transactions, so extreme failure can briefly separate state from the latest event, a gap the recovery slice must continue to narrow.

