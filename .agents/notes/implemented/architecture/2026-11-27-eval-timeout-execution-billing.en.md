# Agent Note: Evaluation timeouts bill execution time

Status: implemented

English | [中文](2026-11-27-eval-timeout-execution-billing.md)

## Problem

An evolution run's evaluations previously measured a fixed 2-hour budget from the submission moment, and validation baselines, per-iteration candidates, test baselines and test finals all shared that single cap. Platform queueing, startup preparation and cross-run capacity reservation all counted as execution time: a production run's test baseline was judged timed out after queueing and executing for more than 2 hours, and a candidate that had just started after queueing for 100 minutes was condemned by the same clock; the size difference between the validation mini-set and the held-out test set was also absent from the budget.

## Decision

`EvalStatus` exposes the platform's `started_at` and `progress.percent`, both optional. The poller's expiry decision splits into two clocks: the execution budget starts at the platform's `running` `started_at`, falling back to HE's `eval_started_at` when the platform omits it; the queue budget starts at `eval_started_at` and only backs up `queued` evaluations. `HE_EVAL_TIMEOUT_SECONDS` (default 2h) still covers validation baselines and per-iteration candidates, the new `HE_EVAL_TEST_TIMEOUT_SECONDS` (default 6h) covers test baselines and test finals, and the new `HE_EVAL_QUEUE_TIMEOUT_SECONDS` (default 6h) is the queue backstop for every evaluation. The `eval_polled` and `eval_timeout` events add `kind`, `startedAt`, `elapsedSeconds`, `queueSeconds` and `progressPercent`, so operators can tell queueing from execution directly. Paused time is still deducted from both clocks.

Evaluation gating and final semantics do not change: a candidate must still strictly beat its baseline, and the test final still uses the test baseline as `init_score`; this decision only changes time accounting and budget tiers. The related gating and final semantics live in [SkillOpt-style baseline gate and test-set final](2026-11-25-baseline-gate-test-final.en.md).

## Alternatives considered

Keep submission-time billing and enlarge the single cap: queueing and execution remain indistinguishable, abnormal queueing still eats the execution budget, and validation and test sets cannot take separate values. Only enlarge the global value by evaluation kind: a test baseline would no longer be falsely killed at 2 hours, but a candidate queued for 100 minutes would still have only 20 minutes of execution budget. Require the evaluation platform to provide a queue SLA or capacity reservation: that is ai-eval-platform scheduling, cannot be verified in this repository, and is outside this issue's boundary. Add a HE database column for the execution start: the platform already supplies the authoritative `started_at`, and persisting it introduces a second source of truth plus a migration cost.

## Consequences

When an older platform response omits `started_at`, the fallback to submission-time billing matches the behavior before this decision and does not block releases. `eval_paused_seconds` remains a coarse cumulative value; a pause that happens before execution starts is also deducted from the execution budget, so it can only under-count, never over-count, execution time. Run-detail and SSE event payloads grow, while frontend display fields stay unchanged. The test-set budget takes a conservative 6 hours and can be tuned to actual platform throughput later.
