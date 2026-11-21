# Add durable safe boundary pause and resume for evolution runs

English | [中文](bugfix-evolution-pause-resume.md)

```yaml flow
kind: issue
id: bugfix-02
milestone: bugfix
depends:
  - m10-06
  - m5-11
priority: P2
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - docs/**
  - .agents/**
adr:
  - ../../notes/implemented/feature/2026-11-20-evolution-pause-resume.md
github:
  number: 436
  url: https://github.com/Shadow-Azure/harness-evolution/issues/436
```

## Background

### Scenario and frontend reproduction

Open http://8.149.232.63/ as admin, then workspace Evolution → Running → run details. On 2026-11-20 a pre-existing systematic-debugging v6.4.1 run displayed running, step 6/7, turn 1/1 and 71%, with no pause, resume or stop-progression action in either list or details. The inspection was read-only: no run was created, cancelled or reconfigured. Production screenshots and full run identifiers remain local.

Users discovering incorrect input, wishing to inspect attribution/candidates, or deferring subsequent model/Git/evaluation work cannot stop at a recoverable boundary. Closing the browser does not stop the backend. Restarting the process interrupts unrelated work and is not a pause. This is a missing control capability, not proof that the observed run is stuck.

### Existing lifecycle and analysis

The four-step wizard previews scope, Sessions, potential cases and attribution. Launch freezes object/ref/digest, workspace, policy, time window and evaluation configuration. One prepare job performs most of UI steps 1–5, builds clusters and prepares Git/turns. Advance generates a patch for a cluster, commits/pushes a candidate and submits evaluation. An independent poller collects results; apply accepts/rejects by external verdict, then the next turn is scheduled. Finalize aggregates/publishes; existing final logic includes placeholder/aggregation behavior, which this issue does not replace.

Durable progress_unit, turn state, commits, external evaluation IDs and idempotent claims make cooperative safe boundary pause feasible with moderate effort. Whole-turn pause is too coarse; immediate process cancellation creates partial work and uncertain external side effects.

### Root causes

- Evolution state.py lacks durable user pause intent, acknowledged pause and a continuation location. Existing states are preparing/running/blocked/completed/failed/interrupted.
- retry.py accepts blocked runs only; interrupted details offer logs. Failure retry is separate from user pause.
- prepare.py executes multiple steps within one job without safe boundaries; mark_prepared and other stale writes can overwrite concurrent control.
- EvolutionJobLifecycle in advance.py, eval_poller.py and blocked_sweeper.py independently schedule subsequent work. A single UI or handler guard is insufficient.
- jobs.py holds a serial worker_lock. Waiting inside a handler would block other runs/sync; CancelledError currently means interrupted.
- Workspace cleanup preserves only preparing/running/blocked and could delete paused workspaces.
- The evaluation gateway offers submit/get_status/get_result, not general external pause/cancel. Wall-clock eval_started_at timeout cannot blindly count a long local pause.

## Goals

- Request pause for preparing/running, show pausing, acknowledge paused only at a safe boundary, and preserve artifacts/run identity.
- Resume only unfinished work without duplicate commits, pushes or evaluation submissions.
- Preserve pause across reload/restart while releasing the worker; keep blocked retry and terminal failure semantics independent.
- Explicitly state that in-flight operations finish and submitted external evaluation may continue.

## Design authority

- [07 §5.11 prepare pipeline](../../../plans/fullstack-design/07-backend-implementation.md#511-v2-流程重排七步与-prepare-管线) and [§6.1 serial runner](../../../plans/fullstack-design/07-backend-implementation.md#61-串行执行器v1).
- [08 §10.2 run details](../../../plans/fullstack-design/08-frontend-implementation.md#102-交互).
- [05 API](../../../plans/fullstack-design/05-api-design.md) and [06 database](../../../plans/fullstack-design/06-database-design.md) host the new contract; existing design does not already define pause.
- Proposed rationale: proposed/feature/2026-11-20-evolution-pause-resume Agent Note.

## Implementation

### Durable control and API

Persist execution-independent control running/pause_requested/paused, actor/timestamps and continuation facts. Use transactional conditional writes for intent, acknowledgement and job/turn claim; terminal completion wins. Make repeated actions idempotent; allow pause from preparing/running and resume from paused, retain retry for blocked, and return explicit 409 for invalid transitions. Proposed space-admin endpoints: POST /api/workspaces/{wid}/evolution/runs/{runId}/pause and /resume. Automatic retry must respect user control.

### safe boundaries and continuation

Check durable boundaries within prepare (association, potential, attribution batches, clustering and workspace preparation), and between patch save, commit, push, evaluation submission, apply and finalize. Define recovery for each intermediate turn state, not only progress_unit. Return normally to release the worker; completion hooks and queued jobs must not advance paused work or lose the sole continuation job.

Resume reconstructs the next action under the same run using stage/turn/artifact/commit/externalId and queues at most one job. Verify uncertain remote push/submission results before retrying. Keep frozen input identities even when refs move. A restart must retain pause instead of marking it interrupted or automatically resuming; retain blocked diagnostics.

### External evaluation and lifecycle

Submitted external evaluation may continue; observers may persist results but cannot apply, launch another turn or finalize while paused. Distinguish actual external failure from local observation timeout; exclude paused time from local unobserved waiting, query existing external state before timeout on resume, and reuse its ID. Protect pause_requested/paused workspaces and candidates from cleanup.

### Frontend and contracts

Add list/detail controls, authoritative action availability, pausing/paused feedback and reload/SSE recovery. Explain current atomic work and external evaluation boundaries. Keep paused runs visible as retained active work. Record actor-aware pause-requested/paused/resumed events distinct from retry. Update FastAPI models, generate OpenAPI/TS and align bilingual design/state mappings; do not edit generated artifacts manually.

## Implementation steps

1. Specify state combinations/safe boundaries and add failing synthetic state/recovery cases.
2. Add both-dialect migrations, conditional repository transitions, APIs/events, permission and concurrency tests.
3. Integrate all stage handlers, lifecycle callbacks, poller, sweeper, workspace retention and restart recovery.
4. Update UI, SSE, generated contracts and bilingual design documents.
5. Exercise fake engines/gateways and temporary Git repositories; capture synthetic before/after UI evidence without touching live runs.

## Dependencies and boundary

Depends on m10-06 and m5-11, delivered as a P2 feature enhancement. The associated PR implements durable pause and continuation, cross-stack regression coverage and prototype comparison without testing on production runs. Continuation reuses frozen inputs; historical inputs that cannot be proven produce an explicit diagnosis instead of guessing a version or matching again.

## Verification

```sh
pnpm contract:generate
pnpm contract:check
pnpm typecheck:api
pnpm typecheck:web
pnpm lint:api
pnpm lint:web
pnpm test:api
pnpm test:db
pnpm test:db:mysql
pnpm test:web
pnpm test:integration
pnpm test:e2e -- --pattern evolution-pause
pnpm verify:flow
pnpm verify:docs
```

Add evolution-pause E2E with fake engines/gateways and temporary Git. Cover prepare, patch, push, evaluating, apply/finalize, restart, repeated actions, another queued run, uncertain side effects and long pause across evaluation timeout. Assert persisted run/cursor/turn/commit/externalId, submission counts, released worker and no post-ack side effects. Use a bounded script for any polling rather than repeated manual commands plus sleep. These are future implementation checks, not claimed results of issue publication.

## Acceptance

- Authorized users request pause from list/details and see requested versus acknowledged states; no promise of instantaneous interruption.
- No new patch/commit/push/evaluation/apply/turn starts after acknowledgement; external results may only be collected.
- Resume preserves run and input identity, reuses completed artifacts and is idempotent.
- Pause survives reload/restart/cleanup; no held worker lock or sweeper progression.
- Blocked facts, terminal races, permissions and cross-space boundaries remain correct.
- Long pause does not cause duplicate external evaluation or false local timeout.
- Both-dialect migrations, API/contracts/SSE, filters/list/details and synthetic cross-stack tests agree.

## Gates and CI

Run focused state/recovery tests, both databases, frontend/backend unit tests and new E2E in CI; maintain at least 80% coverage. Run contract/type/lint, flow and bilingual documentation gates. Commit/PR titles reference this issue number. Evidence excludes production Session text and credentials.

## Non-goals

- No hard kill, token-level continuation, freezing a Git command or external evaluation pause/cancel.
- Do not impersonate blocked/interrupted, restart the service to pause, or roll back published work.
- No pause-time input editing; create a new run for changed conditions.
- No real final-evaluation implementation, attribution algorithm changes, unrelated layout fixes or scheduler rewrite.
