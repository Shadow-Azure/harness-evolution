# Agent Note: Durable Attribution Jobs and Isolated Execution Lane

Status: implemented

English | [中文](2026-11-18-attribution-durable-jobs.md)

## Problem

Attribution becomes long-running, rate-limited, and partially fallible once fixed rules are replaced by a real LLM and Agent. If Run prepare continues to execute each case directly inside the global serial worker, slow calls block sync and unrelated runs. Separate implementations for manual launch, scheduling, and failure retry would also create divergent idempotency, cache, and recovery semantics. Administrators need progress visibility, but observations must not expose raw Traces, Skill content, or credentials.

## Decision

Use `job_runs` as the only source of truth for attribution batches, add persistent claims, leases, maximum attempts, and cancellation flags, and assign `attribution_batch` an isolated bounded handler lane. Run prepare, administrator manual launch, the formal scheduling entrypoint, and retry all call the same `AttributionJobService.submit`, using the Run ID as the active-job idempotency coordinate; do not add an `attribution_only` Run mode. After preparing one Session-context batch, the Runner processes Badcases with bounded concurrency. A case failure does not roll back reports already written, and retry keeps the same job audit row while candidate pointers restrict work to unfinished items. Job results store only executor, Skill revision, batch context hash, counts, cache, latency, Token, warning, and evidence-coverage metrics. Web access permits viewers to read and space admins to launch, cancel, and retry.

## Alternatives considered

Adding an `attribution_only` Run mode would duplicate the same candidate snapshot and stage state in a second lifecycle, so prepare remains the primary orchestrator and attribution becomes a durable batch shared by multiple entrypoints. Keeping attribution on the global worker lock uses less machinery but places unrelated sync work behind real model latency. Creating a new job row for every retry simplifies attempt counting but weakens the audit identity of one logical execution and amplifies duplicate scheduling, so the same row increments its attempt while preserving history and the final result.

## Consequences

Process startup releases unfinished attribution work back to queued, and a worker owns its claim through a short lease and heartbeat; leases and attempt limits prevent unbounded automatic execution. Cancellation propagates to the running batch and its unfinished Badcase tasks, while committed reports remain reusable. The offline executor currently reports zero Tokens; the real intranet adapter must return usage through the executor response. Context observation stores only a batch hash of the per-case manifest context hashes. Deployments must run Alembic `0025_attribution_job_leases` first, and administrators can inspect progress and sanitized errors or operate failed work from the Run’s “Object attribution” step.
