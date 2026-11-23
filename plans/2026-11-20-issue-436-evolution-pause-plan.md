# Evolution pause and resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement #436 durable cooperative checkpoint pause/resume without interrupting other work or duplicating Git/evaluation effects.

**Architecture:** Keep execution status independent from durable `control_state` (`running`, `pause_requested`, `paused`). Persist the continuation job kind/payload, pause actor/times and cumulative paused evaluation time. Reuse frozen run inputs and artifacts; gate every scheduler and stage, release the serial worker on acknowledged pause. Resume atomically creates one continuation job. Existing external evaluation can finish and be observed while paused, without apply or subsequent work.

**Tech Stack:** Python 3.12/FastAPI/SQLAlchemy/Alembic SQLite+MySQL; Vue 3/Vue Query; generated OpenAPI contracts; pytest/Vitest/browser E2E.

**Spec:** `.agents/flow/issues/bugfix-evolution-pause-resume.md`, `plans/fullstack-design/07-backend-implementation.md` §5/6, `08-frontend-implementation.md` §8/10, `plans/ui-prototype-v2/harness-evolution.html`.

## Global Constraints

- User explicitly selects #436, authorizes branch/PR/push/merge/closure, and delegates all design questions to existing documents and prototype; do not pause for design approval.
- Work on `codex/436-evolution-pause-resume` in the requested checkout; retain pre-existing untracked #436 flow/Note files as task inputs.
- No purchased resources or new external services; tests use synthetic data and existing adapters. Production operations remain read-only during inspection.
- API/contract source is FastAPI; never hand-edit generated types. Durable documents bilingual and paired. Notes explain decisions; plans hold review and execution records.
- User requests safe checkpoint pause, not hard cancellation. Never wait for resume while holding the worker lock. Keep terminal/error semantics independent.
- Evidence/screenshots outside repository; final prototype and smoke comparisons linked in PR body. Bounded scripts handle any polling; do not manually sleep/poll.
- No merge before CI, skill-based review/fixes, synthetic GUI smoke and all material issues resolved.

## Review Focus

- Pause racing with claiming work or completion: acknowledgement must fence future effects, terminal completion wins.
- Resume duplicate clicks/restart/queued continuation: preserve one durable continuation, no repeated commit/push/evaluation submission.
- Pause in each prepare substep and candidate intermediate state: save artifacts and resume exact unfinished operation.
- External evaluation finishes during long pause: collect result only, exclude local paused waiting from timeout, query before timeout on resume.
- Cleanup, sweeper, list grouping and role/workspace boundaries: paused work survives and stays visible, other jobs run.

## Task 1: Backend control and recovery

**Files:** `apps/api/app/db/models/evolution.py`, `db/crud/evolution*.py`, new control repository/service modules, new Alembic revision, `service/evolution/{prepare,advance,git_candidate,apply_final,eval_poller,blocked_sweeper,retry,events,runs,stages}.py`, `service/jobs.py`, `main.py`, `api/evolution_workspace.py`, relevant API tests.

**Interfaces:** Add run read fields `controlState`, `pauseRequestedAt`, `pausedAt`, `pausedBy`, `canPause`, `canResume` with backward-compatible defaults. POST workspace run `/pause` and `/resume` use existing admin authorization, return authoritative control facts; repeat requests idempotent, invalid execution status 409, foreign workspace 404. Persist resumable job payload and scheduling transactionally.

- [ ] Write real DB/API tests for request/ack/resume, permissions, duplicates, terminal races and restart; observe RED.
- [ ] Add durable fields/migration/repository and control service; derive availability on server.
- [ ] Integrate stage and batch checkpoints, candidate artifact continuation, all scheduling gates, evaluation observation/timeout, worker/restart and cleanup protection.
- [ ] Verify focused tests GREEN, API lint/typecheck, full backend suite; preserve existing test behavior. Report all unverified corners and baseline failures.

## Task 2: Contracts, frontend, prototype and design

**Files:** `packages/contracts` generated artifacts, frontend API/composables, run list/detail/actions/status components, corresponding tests, `plans/ui-prototype-v2/harness-evolution.html`, fullstack design 05/06/07/08, owning Note and flow pairs.

**Interfaces:** Consume Task 1 generated facts/actions; put pause/resume in existing list/detail action hierarchy, match prototype button/card/token system; disabled pausing state and precise external-evaluation copy. Preserve run navigation and retry semantics.

- [ ] Generate contracts from backend; write failing frontend action/state tests.
- [ ] Add API wrappers and shared action component, invalidate space queries and handle SSE/control events; keep paused runs in active section.
- [ ] Add matching synthetic pause/pausing prototype states and action behavior in existing prototype; update design to document exact backend semantics.
- [ ] Run frontend tests/type/lint and contract checks; record pairing and docs gates.

## Task 3: Integration, review and delivery

**Files:** synthetic `tests/e2e/evolution-pause*.test.mjs` + support, review records under plans; external evidence and polling scripts outside repo.

- [ ] Build synthetic scenarios with two jobs, pause through durable checkpoints and refresh/restart, resume once; external evaluation completed during pause.
- [ ] Compare implementation against all issue acceptance/design and prototype; fix deviations with RED→GREEN tests.
- [ ] Commit/push, create PR and run bounded CI monitoring script; repair failures until green.
- [ ] Apply pr-review, triage findings and pr-review-fix for material issues; fresh reviewer examines concurrency and recovery.
- [ ] Apply computer-use-smoke-reporting to real local browser and prototype at same viewport; reproduce defects with tests, fix/retest until clean. Put screenshots/report in PR description, not Git.
- [ ] Final commit/push and CI; merge PR, update flow to done and close issue only when complete. Follow-up closure PR if required.

## Progress and rulings

- Baseline: main `90835131`; dependencies m10-06/m5-11 done. Branch created; GH CLI not authenticated, user notified asynchronously.
- Resource decision: no purchase required. External eval pause/cancel intentionally excluded; existing task may continue remotely.
- Ruling: branch-in-place follows explicit user workflow; no extra worktree/approval round. Plan decisions derive from issue and existing fullstack/prototype; changes extend missing pause states in both design and prototype.
