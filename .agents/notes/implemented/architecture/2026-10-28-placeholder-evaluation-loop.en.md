# Agent Note: Placeholder evaluation and automatic turn closure

Status: implemented

English | [中文](2026-10-28-placeholder-evaluation-loop.md)

## Problem

After a Git candidate is published, a turn stopped at `evaluating/pending`. The service had no callable evaluation gateway, independent poller, persisted `next_poll_at`, apply handler, or finalize handler. Candidates existed, but the automatic loop could not survive restart or continue a run from evaluation into the next turn and terminal state.

## Decision

`EvalGateway` exposes a stable asynchronous `submit/get_status/get_result` seam; its request, submission, status, and result are immutable internal models, and a gateway is built only from the run's frozen creation-time `eval_config`. The V1 `FakeEvalGateway` stores no process-local task state: its external id is derived from run, turn, and candidate commit, while status and scores come from frozen configuration. The same id therefore remains interpretable after process restart.

`EvolutionEvalSubmitter` submits only in full mode while the run is running, the turn is evaluating, and the candidate was genuinely pushed. An existing `eval_external_id` is reused instead of submitting twice. The external id, evaluating status, attempt, start time, next poll deadline, and aggregate run `eval_status` are committed in one transaction. Local candidates marked `skipped` and cluster-only runs never enter evaluation.

`EvolutionEvalPoller` is an independent process-level lightweight loop and does not occupy a JobRunner worker. Each scan reads persisted turns with `status=evaluating AND eval_status=evaluating AND next_poll_at<=now`. A queued/running response only defers the next deadline by five minutes. A completed result is saved exactly once and queues one `evolution_apply`; failed, timeout, request error, or malformed result enters a sanitized `blocked(eval)` state and is never automatically resubmitted. Timeout fallback uses `eval_started_at + HE_EVAL_TIMEOUT_SECONDS` and wins even when the gateway still reports running.

`EvolutionApplyService` consumes only a durable completed result and uses its external verdict through the real accept/reject candidate boundary. Accepted and rejected are absorbing states, so repeated apply never rewrites a candidate or run branch again. Accept/reject advance the run `progress_unit` in the same transaction, placing the cursor immediately before finalization after the last turn.

After a successful prepare, advance, or apply, terminal lifecycle inspects persisted turns. It queues nothing while a turn is active, queues the next advance while a turn is pending, and queues exactly one finalize after every turn is accepted, rejected, or skipped. `EvolutionFinalizeService` derives a placeholder final row from turn results, validates and fast-forward-publishes only the run branch, and then completes the run. Final-row or final-push failure preserves the facts and enters blocked instead of reporting completion. With `HE_GIT_PUSH=false`, the local terminal state still completes but push status is `skipped`.

## Alternatives considered

Sleeping inside a JobRunner handler occupies the single worker and loses timers on restart. Relying on gateway memory cannot recover evaluation after process restart. Running git from the poller would widen its responsibility and contend with the global worker. Hard-coding apply as acceptance would bypass real amend, candidate force-with-lease, run fast-forward, and reject cleanup, so the service reuses the m5-09 candidate boundary.

## Consequences

A placeholder run now advances automatically from prepare through each candidate, push, evaluation, apply, next turn, and final evaluation. Refresh and restart neither resubmit an existing eval id nor queue duplicate applies. Scores and patches remain placeholders; real external evaluation and patch quality are outside this slice. Automatic backoff, blocked sweeper, crashed-job recovery, and live SSE reconnect remain owned by m5-11.
