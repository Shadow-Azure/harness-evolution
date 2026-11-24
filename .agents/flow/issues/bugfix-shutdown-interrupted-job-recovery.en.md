# Interrupted evolution jobs never resume after a deploy restart: startup recovery skips interrupted rows

English | [中文](bugfix-shutdown-interrupted-job-recovery.md)

```yaml flow
kind: issue
id: bugfix-49
milestone: bugfix
depends:
  - bugfix-11
priority: P2
status: in-progress
scope:
  - apps/api/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 578
  url: https://github.com/Shadow-Azure/harness-evolution/issues/578
```

## Background

### Incident and symptoms

On 2026-11-24 at 14:39 (+08), production run `01M864EY6A9JHK3HKE48EP07T0` (target `skill:codespec-subagent-driven-development@openspec-cn-main-copy-ar-a7ec200-claude-core`, space `OpenSpec-cn_SWE-bench`) started in the prepare stage. At 14:49:51 the run detail page showed "任务被中断，系统将自动恢复；可查看最后事件 job interrupted during shutdown" and the status "已中断". A re-check at 15:15 still found `interrupted`, with no recovery event, no new job, and no retry control on the page.

- Run: `status=interrupted`, `controlState=running`, progress 50% (3/6), stage label "第 4/7 步 · 对象归因中…"; `error={stage: prepare, message: job interrupted during shutdown, at: 2026-11-24T14:49:51+08:00}`.
- Run events: only 5 in total: created at 14:39:00, prepare started, Sessions linked 22/166, 22 potential bad cases; at 14:49:51 `run_interrupted` (`job interrupted during shutdown`, job `01M864EY6AQFE0BTRP50RMEPK7`). There is no `workspace_prepared`, no `clusters_created`, and no `job_recovered` or "进程重启后已自动重新排队".
- Prepare job: `status=interrupted`, `error=job cancelled during shutdown`, started at 14:39:00, finished at 14:49:51.
- Attribution batch job: `01M864EYBQHMZ5E4J8MSA3SSCD` (`attribution_batch`) is also `status=interrupted`, at 9/22 (40.9%), with 6 recorded failures, average latency about 262 seconds and p95 about 312 seconds; it finished at 14:49:51.
- Deployment: Deploy run `45343097443` released `933b143a`; its release log runs `systemctl restart harness-api` at 14:49:26 and starts the health check at 14:49:51. The run's interruption coincides to the second with the end of the default 25-second drain window.

### Root-cause process and conclusion

1. Read the run, events, prepare job, and attribution job through the production page and its authenticated API. The interruption is not a business failure: the run and both jobs are `interrupted`, all three errors come from the shutdown path, and the attribution batch was still making progress (9/22).
2. Compare Deploy run `45343097443`'s release log: `harness-api` restarts at 14:49:26 and the health check starts at 14:49:51. The run's `error.at` matches the end of the drain window to the second, confirming that the release restart triggered the interruption.
3. Read the shutdown path `JobRunner.close()` / `_drain_and_cancel()`: after SIGTERM it waits at most `HE_JOB_DRAIN_TIMEOUT_SECONDS` (25 seconds by default) and then cancels the active handler. The `CancelledError` branch in `_run()` calls `JobRepository.interrupt()`, which moves the job from `running` to the terminal state `interrupted` and records `run_interrupted`.
4. Read startup recovery `JobRunner.recover()`: it first calls `requeue_running_kind("attribution_batch")` and then `mark_running_interrupted("process restarted")`; both match only `status=running`. The restart happened after the old process had already written `interrupted`, so neither query sees these rows, `_requeue_interrupted()` never runs, and no recovery event or replacement job is written.
5. Read the frontend and retry entrypoints: `RunDetail.vue` shows "系统将自动恢复" for `interrupted`; `/runs/{id}/retry` accepts only `blocked` and `retry.py` rejects every other status. The page's recovery promise has no backend implementation, so the run can only be handled manually.

**Conclusion**: The direct trigger is the production release restart at 14:49:26. The root cause is a broken state contract between shutdown and startup recovery. Graceful shutdown writes running jobs into the terminal `interrupted` state, while startup recovery only adopts rows that are still `running`; an `interrupted` row has no requeue path. As a result, every `evolution_prepare` that crosses a release, together with the `attribution_batch` it waits on, stays permanently interrupted, contradicting the page's promise that the system will recover automatically. This is the remaining gap in #474's acceptance criterion "after the drain timeout, the job is released safely and taken over by the recovery flow": #474 tested recovery when a crashed process left a job `running`, but not recovery after graceful shutdown has already written `interrupted`.

**Limitation**: There was no SSH access to the production host and no access to `journalctl`; the conclusion rests on the persisted run/job state, the event timeline, the Deploy run log, and the shutdown/recovery code paths. The run was not re-executed and no production data was modified.

## Goals

- The single recommended solution: make startup recovery adopt jobs that graceful shutdown marked `interrupted`, instead of adopting only `running` rows. After a restart, automatically requeue interrupted evolution jobs and attribution batches so the run continues from its persisted stage boundary, with no manual retry and no repeated completed attribution work.
- Concrete semantics:
  - `attribution_batch`: reset a job interrupted by shutdown back to `queued`, preserving the batch identity, progress, and completed results; the recovered parent prepare joins the same batch.
  - `evolution_prepare` / `advance` / `apply` / `finalize` / `retry`: recover only the latest interrupted job per `(kind, ref_id)` and requeue it through `EvolutionControlRepository`'s run-state, pause, and blocked fencing; completed or blocked runs are not recovered.
  - Record a `job_recovered` event and call `start_queued()` to dispatch; keep the original `run_interrupted` event and do not overwrite it.
  - Idempotence: after recovery the job is no longer `interrupted`, so a second restart does not enqueue it again; runs with `pause_requested` / `paused` are not recovered automatically.
- This directly fixes the root cause (the terminal state has no recovery path) and does not depend on a longer drain, a release freeze, or a manual retry click.

## Design authority

- [07 §5.8.1 blocked retry policy](../../../plans/fullstack-design/07-backend-implementation.md#581-阻塞重试策略): the existing blocked/retry semantics; this issue only adds `interrupted` recovery and does not change blocked.
- [07 §5.6 single-iteration execution](../../../plans/fullstack-design/07-backend-implementation.md#56-单轮执行candidate--push--提交评测fullevolutionengineadvance_one_round): stage boundaries and saved progress; recovery continues from the persisted stage.
- [06 §3.9 job_runs](../../../plans/fullstack-design/06-database-design.md#39-job_runs--统一任务表): the job state machine and lease columns; this issue queries recoverable rows by `status=interrupted`.
- [06 §5.7 evolution_run_events](../../../plans/fullstack-design/06-database-design.md#57-evolution_run_events--执行过程与异常追加): the event contract for `run_interrupted` / `job_recovered`.
- [04 §3 layering and directories](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录): recovery orchestration stays in service, state queries stay in db.
- #474 (bugfix-11): the existing lease, heartbeat, drain, and startup recovery implementation; this issue fixes its uncovered graceful-shutdown branch.
- Shutdown configuration: `KillMode=mixed` + `TimeoutStopSec=45` in `deploy/harness-api.service`, and the restart-drain notes in `docs/deployment.md`.

## Implementation

1. Query and state: add a "latest shutdown interruption" query in `JobRepository`, selecting `status=interrupted`, recoverable `kind`, `attempt < max_attempts`, `cancel_requested=false`, and the latest row per `(kind, ref_id)`; only rows whose run is still active with `control_state=running` qualify.
2. Startup recovery: after the existing `mark_running_interrupted()`, extend `JobRunner.recover()` to recover those rows:
   - `attribution_batch`: reuse `requeue_running_kind`'s reset semantics (`status→queued`, clear lease/error), but match `interrupted` rows; do not re-execute completed cases.
   - Evolution jobs: requeue through the same `EvolutionControlRepository.requeue_interrupted` fence; skip when `control_state != running`, `status` is `completed` / `failed` / `blocked`, an active job already exists, or `resumed_at >= finished_at`.
   - Record `_record_recovery()`; do not write another "process restarted" interruption for rows that are already `interrupted`, to avoid duplicate events.
3. Dispatch and ordering: recovery only enqueues, and `start_queued()` dispatches at the end; enqueue the attribution batch before its parent prepare so `run_for_prepare` can join the same batch.
4. Observability: the recovery event carries `previousJobId`, `jobId`, and `stage`; startup logs summarize recovered rows, kinds, and runs; never log Session content or credentials.
5. Tests: add `apps/api/tests/bugfix-49-shutdown-recovery/` covering shutdown-then-restart, idempotence, fencing, and resuming a 9/22 batch.
6. Documentation: align the restart-drain notes in `docs/deployment.md` / `docs/deployment.en.md` with the implementation; if a new event type is required, update the contract via 06 §5.7 first.

## Implementation steps

1. Add the job query and unit tests: select the latest shutdown-interrupted row per kind/ref, and prove historical rows cannot be selected again.
2. Change `recover()`: adopt `interrupted` rows, enqueue attribution batches and evolution jobs separately, and record the recovery event.
3. Wire the control fence: exclude paused/blocked/active jobs and keep at most one replacement per run and kind.
4. Add regression tests: close→recover, a second recover, paused/blocked runs, and a 9/22 batch resume.
5. Run the gates and update the deployment docs; record verification evidence under this issue.

## Dependencies and boundary

- Dependencies: the lease/heartbeat/drain and `_INTERRUPTIBLE_KINDS` delivered by bugfix-11 (#474); the process recovery and event semantics from m5-11.
- Boundary: this issue only makes startup recovery adopt `interrupted` rows. It does not change the seven-step algorithm, the attribution runner, Git idempotence, the deployment flow, or the UI status wording, and it does not introduce an external orchestrator or multi-instance leader election.
- Real blocked/failed jobs are not recovered as success; only shutdown interruptions are recovered.

## Verification

```sh
pnpm test:api -- tests/bugfix-49-shutdown-recovery
pnpm test:api -- tests/bugfix-11-durable-jobs
pnpm test:api -- tests/m5-11-evolution-recovery
pnpm test:db
pnpm typecheck:api
pnpm verify:flow
pnpm test:gates
```

- Simulate the drain timeout: prepare and attribution_batch both end as `interrupted`; after a restart recovery both jobs become `queued`, prepare continues from `progress_unit=3`, attribution only fills unfinished cases, and the run no longer stays `interrupted`.
- Two consecutive recoveries enqueue only once; paused/blocked runs are not recovered.
- In a production-equivalent scenario (22 cases, 9 completed), the completed count only grows after recovery and completed cases are not called again.

## Acceptance

- After graceful shutdown (deploy or `kill -TERM`) marks active jobs `interrupted`, the next startup requeues and continues them without manual action; a `job_recovered` event appears and the run is no longer permanently `interrupted`.
- Both the `attribution_batch` and its parent `evolution_prepare` recover; recovery does not repeat completed attribution results.
- Runs that are paused, blocked, or completed are not recovered automatically; a second restart does not create duplicate jobs.
- Production-equivalent tests cover the 9/22 batch boundary; documentation and event semantics agree.

## Gates and CI

- `pnpm test:api`, `pnpm test:db`, `pnpm typecheck:api`, `pnpm verify:flow`, `pnpm test:gates`; run `pnpm lint:docs` when documentation changes.
- The new restart/resume tests must run in CI; production logs, Session content, and credentials must not be committed.

## Non-goals

- Do not avoid the problem by extending the drain timeout or freezing release windows, and do not depend on a manual retry.
- Do not change the retry semantics of blocked jobs and real failures.
- Do not change the seven-step engine algorithm, the attribution Skill, Git push idempotence, or the UI design.
- Do not add multi-instance leader election or an external workflow engine.
