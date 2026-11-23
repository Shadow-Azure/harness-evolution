# Durable job leases, heartbeats, and auto-resume across deployment restarts

English | [中文](bugfix-deploy-interrupt-recovery.md)

```yaml flow
kind: issue
id: bugfix-11
milestone: bugfix
depends:
  - bugfix-09
  - m5-11
priority: P2
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - deploy/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 474
  url: https://github.com/Shadow-Azure/harness-evolution/issues/474
```

## Background

On 2026-11-21 at 16:07 (+08), a production evolution run `01M7YJAGVW1QKDMA7ECEX1EHT7` (target `skill:systematic-debugging@v6.4.1`) ended in prepare with `blocked(push)` and `run branch publication failed`. The multi-host push provider from #457 (PR #465, merge commit `32170f9`) had been merged at 15:07 and deployed successfully at 15:17, so the question was whether the provider had failed or a different interruption had occurred.

### Symptoms

- Run API/events: `status=blocked`, `blockedStage=push`, `push_status=failed`; the event stream jumps from "clusters created" to `run branch publication failed` with no `workspace_prepared`, so the publish step never completed. The run detail keeps only the generic message.
- GitHub: the fork `Shadow-Azure/superpowers` was created at 16:07:22 (2 seconds after the run was created); the run branch `evo/20261121-01M7YJAGVW1QKDMA7ECEX1EHT7` already existed at 16:07:32 and its head `5bf4e780` is exactly the `v6.4.1` tag commit. `ensure_fork`, the PAT, the push URL, and the remote write all succeeded.
- Deployment: Deploy #156 (releasing `136aa92`) switched `current` at 16:07:33.077 and restarted `harness-api` at 16:07:33.080; the run's `error.at` is also 16:07:33 (+08), the same second.
- Code/shutdown path: the `git push` inside `_push_run_branch` is the last prepare step. `harness-api.service` does not override systemd's default `KillMode=control-group`, so a restart also terminates the git child process; the application's `jobs.close()` also cancels in-flight tasks. When the remote ref has been written but the client is killed while finishing, `git push` exits non-zero and `classify_git_failure` records `blocked(push)`.
- Message overwrite: `_prepare_workspace` first calls `mark_blocked()` with the detailed reason, then `RunBlocked("run branch publication failed")` reaches the job layer's `record_blocked()`, which overwrites `error_message`/`push_error` with the generic text. `GitOperationError` keeps only fixed phrases and no stderr, so API/UI cannot distinguish a deployment interruption from a permission/network failure.

### Root-cause process and conclusion

The investigation followed "prove whether the provider worked, then locate the failure":

1. Read the run detail and events; the failing stage is push and prepare never completed.
2. Check the fork and the run branch; the remote write succeeded, ruling out PAT, fork, push URL, and non-fast-forward issues on the provider side.
3. Compare Deploy #156's release log with the run's `error.at`; the restart and the failure fall in the same second.
4. Read `GitWorkspaceManager`, the job runner, and the systemd unit; the git child is terminated by the service restart, the non-zero push takes the blocked path, and the generic text overwrites the detail.

**Conclusion**: This was not a #457/#465 provider failure. The direct cause is that the run overlapped Deploy #156's release window: `harness-api` restarted at 16:07:33.080 and terminated the `git push` while it was finishing. The remote branch was updated but the client exited non-zero, so the run was marked `blocked(push)`. The secondary problem is that interruptions and real push failures are not distinguished, and the detailed error is overwritten, so the incident looks like a provider fault.

**Limitation**: There was no SSH access to the production host and no access to `journalctl` or the raw git stderr; the conclusion rests on second-level timestamp alignment, the existing remote branch, the incomplete prepare, and the shutdown code path. The run's retry was not triggered.

### Why this needs its own issue

- The proxy/credential problem was fixed by #457, but a deployment restart can still push an in-flight job into blocked and require a manual retry; the same interruption can happen during iteration, evaluation, and finalization.
- Interruptions are recorded as blocked with the detail lost, so operators cannot distinguish "deployment restart", "network failure", and "insufficient permission".
- The long-term fix is recoverable jobs (lease + heartbeat + auto-resume), not more retries or manual deployment freezes.

## Goals

- Jobs carry a lease and heartbeat: claiming a job writes a lease owner/expiry, a periodic heartbeat renews it, and after a process exits the expired lease allows another worker to take over. Single-instance deployments still recover primarily at startup; the lease fields prepare for multi-instance and liveness detection later.
- Startup/restart automatically recovers interrupted jobs: no `failed`/`blocked` waiting for a human; resume from the last saved stage boundary. Use the existing `interrupted` run state and record `run_interrupted` / `job_recovered` events.
- Key stages are idempotent:
  - prepare/push: persist the run's push target, base commit, and run branch; on recovery, reconcile with `ls-remote` first. If the remote ref already equals the target commit, skip the push; otherwise push again. Never recreate a branch or duplicate a commit.
  - iteration/evaluation/finalization: use the iteration, candidate tag, and eval request as idempotency keys; on recovery reuse the committed candidate/tag and completed eval result without calling models or evaluation again.
- Shutdown semantics: after SIGTERM, stop claiming new jobs and give in-flight jobs a bounded drain window. Finish within the window normally; otherwise release the lease and mark `interrupted`, and let recovery take over. The deployment unit uses `KillMode=mixed` + `TimeoutStopSec` so git children are not killed by default.
- Error classification and observability: distinguish `interrupted` (process/deployment) from a real `blocked(push)` (permission/network/non-fast-forward); keep the detail (`error_detail` on events) instead of letting the generic `RunBlocked` text overwrite it. The UI shows "interrupted by deployment restart, resuming/recovered".
- Compatibility: do not change #457's provider, fork, or credential-injection semantics; real permission/network failures still enter blocked and can be retried manually; existing run/job data remains readable.

## Design authority

- [07 §5.8.1 blocked retry policy](../../../plans/fullstack-design/07-backend-implementation.md#581-阻塞重试策略): the existing blocked/retry semantics; this issue adds recoverable execution on top rather than replacing them.
- [07 §5.6 single-iteration execution](../../../plans/fullstack-design/07-backend-implementation.md#56-单轮执行candidate--push--提交评测fullevolutionengineadvance_one_round): the candidate → push → eval stage boundaries and idempotency points.
- [06 §3.9 job_runs](../../../plans/fullstack-design/06-database-design.md#39-job_runs--统一任务表): the existing job states and columns; this issue adds lease/heartbeat fields.
- [06 §5.7 evolution_run_events](../../../plans/fullstack-design/06-database-design.md#57-evolution_run_events--执行过程与异常追加): the storage contract for `run_interrupted`/`push_*` events and `error_detail`.
- [04 §3 layering and directories](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录): job/lease logic stays in service and db layers; git processes and host differences stay in third_party_api.
- systemd stop semantics: [systemd.kill](https://freedesktop.org/software/systemd/man/247/systemd.kill.html) (the default is `KillMode=control-group`; `mixed` sends SIGTERM only to the main process, then SIGKILLs the rest after the timeout).
- Kubernetes graceful termination: `terminationGracePeriodSeconds` and `preStop` drain patterns, [Pod lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination).
- Durable-execution retry and recovery patterns: [Temporal failures and error handling](https://docs.temporal.io/encyclopedia/failures-and-error-handling).

## Implementation

### 1. Job leases and heartbeats

- Add `lease_owner` (instance/task identity), `lease_expires_at`, and `heartbeat_at` to `job_runs`; the migration adds the columns and a `(status, lease_expires_at)` index, and existing rows are treated as expired.
- Change `JobRepository.claim()` from "queued only" to an atomic claim of "queued or a running row with an expired lease"; add `renew()` for periodic heartbeats and `release()` to release the lease during shutdown while keeping the job recoverable; a crashed worker is taken over by the next startup or scan.
- In a single instance, startup recovery can still treat every residual running row as this process's own; the lease fields make expiry explicit and keep the path safe for future multi-instance deployments.

### 2. Startup recovery and auto-resume

- `JobRunner.recover()`: mark residual running jobs `interrupted`, record `run_interrupted`, and re-enqueue recoverable evolution jobs (replacing the current `_INTERRUPTIBLE_KINDS`, which only re-enqueues `sync`).
- Stage-specific resume enters `EvolutionPrepareService` / `EvolutionCandidateService` / apply/final and reuses the persisted workspace, iteration, candidate, and eval records; it does not rerun all seven steps from the beginning.
- Run state: use the existing `interrupted` state to show the interruption and return to `running` after recovery; events keep `jobId`, `stage`, and `attempt` so the UI can correlate them.

### 3. Push reconciliation and idempotency

- Add read-only reconciliation in `third_party_api/git/workspace.py`: `remote_ref_commit()` already reads remote refs. Before pushing, prepare persists the target commit and push URL; on recovery it compares the remote head first:
  - remote equals the target commit → treat as already published and continue;
  - remote is missing or behind → use the existing fast-forward push;
  - remote cannot fast-forward → still treat as a real push failure, never swallow it.
- When `git push` exits non-zero, run one `ls-remote` reconciliation before deciding failure: if the remote already holds the target commit, treat it as success (this covers the "remote written, client killed" case).
- Candidate tags and final branches use the same idempotency keys (candidate ref + commit, run branch + commit); recovery reuses existing refs instead of amending or force-pushing again.
- The provider interface and credential semantics are unchanged; reconciliation is read-only and never writes the token into URLs, logs, or events.

### 4. Shutdown drain and deployment coordination

- Application shutdown: stop claiming new jobs, wait for in-flight jobs up to `drain_timeout`, then release the lease and mark `interrupted` for startup recovery. The current `jobs.close()` cancels immediately and must become a bounded drain.
- systemd: add `KillMode=mixed` and `TimeoutStopSec` (greater than the drain window) to `deploy/harness-api.service` so the main process receives SIGTERM first and can drain, and git children are not killed by default. The migration/switch/health-check/rollback order in `release.sh` stays unchanged.
- Optional deploy-side queueing/freeze (not implemented here): until drain is available, operators should still avoid starting runs during a release window.

### 5. Error classification, events, and UI

- Keep `classify_git_failure` mapping real push failures to `blocked(push)`; add a process/deployment interruption classification and fix the overwrite where `_prepare_workspace`'s detailed message is replaced by the job layer's `RunBlocked`: blocked records are written only for real failures, while interruptions go through `run_interrupted`.
- Events keep `error_type`, `error_message`, and `error_detail`; push events record remote, branch, commit, and the reconciliation result (never the token).
- Run detail/list shows "interrupted by deployment restart, auto-recovered/resuming" with an event timeline instead of the generic `run branch publication failed`.
- If new contract fields/states are needed (for example, recovery count or source), change `packages/contracts` first and run `pnpm contract:generate`; existing blocked field semantics stay unchanged.

## Implementation steps

1. Data model and migration: lease/heartbeat columns, indexes, atomic `claim/renew/release`, and tests.
2. Startup recovery: residual running → interrupted + automatic re-enqueue, with tests for restart during prepare/advance/apply/final.
3. prepare/push idempotency and reconciliation: persist the push target and target commit; simulate "remote updated but push non-zero"; reuse the remote ref without pushing again.
4. Shutdown drain: stop claiming, bounded wait, lease release; systemd `KillMode=mixed`/`TimeoutStopSec`; deploy script and docs.
5. Iteration/evaluation/finalization recovery: iteration/candidate/eval idempotency keys, reuse completed results, add recovery tests.
6. UI and API: interrupted/resuming/recovered states, event timeline, error-detail display; update contracts as needed.
7. Docs and an Agent Note (architecture): record lease/recovery boundaries, the single-instance assumption, and the multi-instance evolution; finish gates and E2E.

## Dependencies and boundary

- Depends on #457 (bugfix-09, multi-host provider and per-run push target) and m5-11 (#60, blocked backoff, events, and existing process-recovery semantics).
- Boundary: this issue only covers recoverable jobs and interruption semantics. It does not introduce an external workflow engine, change provider/fork/PAT injection, implement multi-instance leader election, or productize deploy freezes/release windows.
- Phasing: prepare/push recovery and reconciliation must ship first and be independently verifiable; iteration/evaluation/finalization recovery may follow in the same issue, but leases without recovery are not a deliverable.
- Real permission failures, network failures, and non-fast-forwards still follow blocked + manual retry; real failures must not be auto-retried into "success".

## Verification

```sh
pnpm test:api -- tests/bugfix-11-durable-jobs
pnpm test:api -- tests/bugfix-11-prepare-resume
pnpm test:db
pnpm test:web
pnpm test:e2e -- --pattern bugfix-11
pnpm typecheck
pnpm contract:check
pnpm verify:flow
```

- Simulate the remote branch already being updated while `git push` exits non-zero: recovery's `ls-remote` reconciliation hits, the duplicate push is skipped, the run continues, and it never enters blocked.
- Simulate a process restart with a running job: startup recovery marks interrupted, records `run_interrupted`, and re-enqueues; the resumed job continues from prepare/push or the corresponding stage instead of rerunning from scratch.
- Simulate a real 403/non-fast-forward: the run still enters `blocked(push)`, and the error detail is visible in events/detail instead of being overwritten by the generic message.
- Simulate shutdown drain: SIGTERM within the window finishes normally; after the timeout the lease is released, the job is marked interrupted, and the next startup takes over.
- Data: job/run rows remain readable before and after migration; rows without a lease are treated as expired; SQLite and MySQL migration tests pass.
- UI: run detail shows interrupted/resuming/recovered and does not show the misleading generic push failure.

## Acceptance

- A deployment restart (or `kill -TERM`) after prepare/push lets the run continue automatically without a manual retry; the remote ref matches the target commit, with no duplicate push and no duplicate branch.
- A restart during iteration/evaluation/finalization reuses the completed candidate/tag/iteration/eval and does not call models or evaluation again (asserted with idempotency keys and events).
- Interruptions and real failures are distinguishable: interruptions are `interrupted` and auto-recover; permission/network/non-fast-forward failures remain `blocked(push)` with details preserved.
- Shutdown drain is bounded and deployments do not wait forever; after the timeout the job is safely released and taken over by recovery.
- Migrations, events, API, UI, docs, and gates are complete; existing blocked/retry and provider behavior do not regress.

## Gates and CI

- `pnpm test:api`, `pnpm test:db`, `pnpm test:web`, `pnpm test:e2e`, `pnpm typecheck`, `pnpm contract:check` (when contracts change), `pnpm verify:flow`, `pnpm lint:docs`, `pnpm test:gates`.
- New restart/resume tests must run in CI; migration tests cover SQLite/MySQL; no production logs, Session content, or credentials enter the repository.

## Non-goals

- Do not introduce Temporal/Celery or another external orchestrator; do not implement multi-instance leader election or distributed locks (single-instance leases first, evolve later).
- Do not change #457's provider, fork, PAT injection, or existing failure classification.
- Do not auto-retry real permission/network failures into "success"; blocked remains the manual path.
- Do not productize deployment freezes/release windows; operators can drain deployments manually first.
- Do not refactor the seven-step engine's algorithms, UI, or evaluation protocol.
