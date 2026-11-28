# Evolution eval timeout starts at submission and ignores evaluation kind, so queue time and large test sets cause false timeouts

English | [中文](bugfix-eval-timeout-queue-and-kind.md)

```yaml flow
kind: issue
id: bugfix-72
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/third_party_api/**
  - apps/api/app/config.py
  - apps/api/app/main.py
  - apps/api/tests/**
  - .env.example
  - .agents/notes/**
  - .agents/flow/issues/**
  - plans/**
adr: []
github:
  number: 659
  url: https://github.com/Shadow-Azure/harness-evolution/issues/659
```

## Background

### Symptoms

Production evolution run [`01M8DEKFZ5R70HARCQZW562BGR`](http://8.149.232.63/workspaces/01M7KJ05ENF9784GPBDV544VB0/evolution/runs/01M8DEKFZ5R70HARCQZW562BGR) (target `codespec-subagent-driven-development`, base `59bebcfe`, created 2026-11-27 10:50) was blocked at step 6/7, iteration. The run detail showed:

- `status=blocked`, `blockedStage=eval`, `error.stage=eval`, `error.message="evaluation timed out"`;
- terminal time `2026-11-27T12:55:42+08:00`;
- the `eval_timeout` payload was `{"kind":"test_baseline","externalId":"78369938-bdb3-45bb-9c1e-deed8fdfbf84","status":"timeout"}`, not the turn-1 candidate evaluation.

The evaluation timeline from the raw events (`GET /api/workspaces/{wid}/evolution/runs/{rid}/events`):

| Time (+08:00) | Event | Key fields |
|---|---|---|
| 10:54:38 | Validation baseline submitted | `291187d7-30fd-4893-b98b-967813e6439f` |
| 10:54:40 | Test baseline submitted | `78369938-bdb3-45bb-9c1e-deed8fdfbf84`, `kind=test_baseline` |
| 11:11:34 | Turn-1 candidate evaluation submitted | `87aa26d2-21e7-45c7-9e14-39422a663b6a` |
| 11:55:08 | Validation baseline completed | about 60m30s from submission |
| 11:16:34–12:46:42 | Candidate evaluation stayed `queued` | polled every 5 minutes; first `running` at 12:52:12, 100m38s after submission |
| 12:50:42 | Test baseline was still `running` | about 1h56m after submission |
| 12:52:12 | Candidate evaluation first became `running` | 100m38s after submission |
| 12:55:42 | Test baseline timed out and the run was blocked | 2h1m2s after test-baseline submission; the candidate had actually run for only about 3m30s |

In other words: the evaluation that timed out was the **test baseline**, and the candidate evaluation had just started when the run was killed. The run was not blocked because the candidate failed or timed out.

### Investigation

1. Logged into the production API with the administrator account, read the run detail and all 76 events, and confirmed that the `eval_timeout` `kind` is `test_baseline` while the candidate turn (`roundId=01M8DET5GNQY8YG1AXEQSM2K2R`) was still `running` at 12:52:12.
2. Compared event times with the time fields in code: `EvolutionEvalSubmitter` writes `started_at=now` into `evolution_rounds.eval_started_at` / `evolution_evaluations.eval_started_at` at submission, and `EvolutionEvalPoller._expire_if_due` / `_expire_run_if_due` compare `now - eval_started_at` with a fixed `timeout`. The two hours therefore start at **submission time**, not when the platform starts executing.
3. Checked the `ai-eval-platform` `/api/v1/eval-runs/{id}/status` contract: the status response carries `status`, `progress`, `started_at` and `duration_seconds`; `preparing`/`queued` map to HE `queued`, `running`/`finalizing` map to HE `running`. HE's `AiEvalPlatformGateway.get_status` currently keeps only `status` and drops `started_at` and `progress`, so the poller cannot distinguish queueing from execution.
4. Checked the platform capacity implementation ([`capacity.py`](https://github.com/Shadow-Azure/ai-eval-platform/blob/main/backend/app/services/capacity.py) and [`dispatcher.py`](https://github.com/Shadow-Azure/ai-eval-platform/blob/main/backend/app/services/dispatcher.py)): on one resource pool a later evaluation may only use `pool_max - in-flight attempts of other runs`. This run submitted the validation baseline, the test baseline and the candidate together at startup; the candidate's `queued` interval (11:16–12:46) exactly overlaps the test baseline's `running` interval, and under the platform's cross-run capacity reservation the earlier test baseline holds the slots the candidate needs. That is the most direct capacity source for the 100-minute queue. That scheduling problem is tracked separately by #656 "Run the test-set baseline and final evaluation together at the final stage"; this issue does not duplicate it.
5. Checked other runs: the two real-platform runs from 2026-11-26 (`01M8AJ3WS9D5H16F2WHV5A1K74`, `01M8BTSPJA3XBB8WY2T5B7219E`) also submitted both baselines at startup and their candidates also stayed `queued` for a long time, so this is not a one-off.

### Root cause

1. **The timeout is charged from submission, so queue time counts as execution time.** The candidate was submitted at 11:11:34 and only became `running` at 12:52:12; queueing consumed 100 of its 120 minutes. Even without the test baseline timing out first, it would have been declared timed out at 13:11:34 after only about 19 minutes of execution. This is a direct consequence of `_expire_if_due` / `_expire_run_if_due` using `eval_started_at` regardless of whether the platform has started executing.
2. **Every evaluation kind shares the same 2-hour hard cap.** `HE_EVAL_TIMEOUT_SECONDS` defaults to 7200 and applies identically to the validation baseline, each candidate, the test baseline and the test final. The test set is the held-out set; its case count and per-case budget cannot be assumed to match the validation mini-set. On the platform side `case_timeout_seconds` defaults to 3600 and `max_attempts` to 2, and cases run in shards bounded by pool capacity; a single test-set evaluation cannot fit in two hours. The test baseline in this run was still `running` at the 2-hour mark, which is direct evidence that the budget does not match the workload.
3. **Timeout diagnostics do not expose the distinction.** `EvalStatus` only has `status` and an optional `message`, and `eval_polled` records only the platform status string, with no `startedAt` or completion percentage. Operators see only the final `evaluation timed out` and cannot tell whether the platform was queueing, executing slowly, or truly stuck.

## Goals

- Charge the evaluation timeout only for time the platform actually executes: `queued`/`preparing` consumes no execution budget; the clock starts on `running`.
- Set budgets by evaluation kind: the validation baseline and turn candidates keep the 2-hour execution cap; the test baseline and test final get a larger, configurable execution cap.
- Still detect genuinely stuck evaluations: queueing and execution each have an observable fallback bound, and timeout events show which phase was stuck and for how long.
- Do not change evaluation gating or final semantics: a candidate must still be strictly better than its baseline, and the test final still uses the test baseline as `init_score`.

## Design authority

- [07 §5.7 Evaluation access and polling](../../../plans/fullstack-design/07-backend-implementation.md): the existing `HE_EVAL_TIMEOUT_SECONDS`, 5-minute polling and `failed/timeout → blocked` path; this issue changes "charged from submission" to "charged from execution" and adds per-kind budgets.
- [04 §5 Configuration](../../../plans/fullstack-design/04-backend-architecture.md): where `HE_EVAL_POLL_SECONDS=300` and `HE_EVAL_TIMEOUT_SECONDS=7200` are defined; this issue adds a test-set budget and a queue budget.
- [Agent Note: SkillOpt-style baseline gate and test-set final](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-25-baseline-gate-test-final.md): the existing run-level evaluation, test baseline and final semantics; this issue only changes timeout accounting, not the compared objects.
- [#656 Run the test-set baseline and final evaluation together at the final stage](https://github.com/Shadow-Azure/harness-evolution/issues/656): removes test-baseline contention with the candidate; this issue is orthogonal, but both must land, otherwise the two test-set evaluations at the final stage will still be falsely killed at the 2-hour mark.
- Platform status contract: `GET /api/v1/eval-runs/{id}/status` returns `started_at`, `progress` and `duration_seconds` ([`results.py`](https://github.com/Shadow-Azure/ai-eval-platform/blob/main/backend/app/api/results.py)); this is the authoritative source for the execution start and needs no new HE database column.

## Implementation

### 1. Expose execution start time and progress from the gateway

- Add optional fields to `EvalStatus` in `service/evolution/engine/contracts.py`: `started_at: datetime | None` and `progress_percent: float | None` (the latter is observational and may be empty).
- In `get_status` in `third_party_api/eval_gateway/ai_eval_platform.py`, parse `started_at` (ISO-8601 with an offset) and `progress.percent` from the platform response; when parsing fails the field is `None` and the status decision is unchanged.
- Let the fake gateway in `third_party_api/eval_gateway/fake.py` return `started_at` so tests can construct "queue first, execute later" scenarios.

### 2. Charge the timeout by execution time and separate queueing

- In `_expire_if_due` and `_expire_run_if_due` in `service/evolution/eval_poller.py`:
  - When the platform status is `running`, use `status.started_at` as the execution start; when the platform does not return it, fall back to `eval_started_at` (compatible with older platforms and identical to today's behavior).
  - When the platform status is `queued`, do not check the execution timeout; compare `eval_started_at` against a queue bound `HE_EVAL_QUEUE_TIMEOUT_SECONDS` (default 21600 seconds, 6 hours) so a permanently queued platform run cannot leave the HE run hanging forever.
  - Add `startedAt`, `elapsedSeconds`, `queueSeconds` and `progressPercent` to timeout event payloads, and add them to `eval_polled` as well, so queueing and execution are distinguishable.
- The queue bound is only a safety net and does not participate in the normal execution budget; genuine stuck detection remains with the candidate/test-set execution budgets.

### 3. Budgets by evaluation kind

- Add `eval_queue_timeout_seconds` and `eval_test_timeout_seconds` to `config.py`:
  - `HE_EVAL_TIMEOUT_SECONDS` (default 7200): execution cap for the validation baseline and turn candidates, unchanged.
  - `HE_EVAL_TEST_TIMEOUT_SECONDS` (default 21600): execution cap for the test baseline and test final; test-set case counts, platform sharding and retries are all larger, so 6 hours is a conservative first value that can be tuned to platform throughput.
  - `HE_EVAL_QUEUE_TIMEOUT_SECONDS` (default 21600): the longest queue time for any evaluation, measured from submission.
- Pass all three into `EvolutionEvalPoller` in `main.py`; `eval_poller` selects the budget by kind: `run_evaluation.kind in {"test_baseline","test_final"}` uses the test budget, while turn candidates and `validation_baseline` use the candidate budget.
- Add the three variables with comments and defaults to `.env.example`, and update the configuration table in `plans/fullstack-design/04-backend-architecture.md` so docs and code do not drift.

### 4. Test coverage

- In `apps/api/tests/m12-03-real-patch-eval/test_eval_poll_transient.py`, add a case that queues for 3 hours and then runs for 30 minutes, asserting that no `eval_timeout` is produced and that `eval_started_at` is not rewritten.
- Add a case that queues a candidate for 100 minutes and then runs it for 2 hours 1 minute, asserting the timeout fires only after 2 hours of execution rather than early from submission time.
- Add a case where the test baseline runs for 2.5 hours and assert it does not time out under the 6-hour test budget; setting the test budget back to 2 hours must still time out as expected.
- Add a case where queueing exceeds `HE_EVAL_QUEUE_TIMEOUT_SECONDS`, asserting a queue-timeout block with `queueSeconds` recorded.
- Reuse the baseline/final fixtures in `apps/api/tests/bugfix-63-real-eval/test_run_evaluations.py` so #656's submission-timing change and this issue's budget change can pass together.

## Implementation steps

1. Extend `EvalStatus` and `AiEvalPlatformGateway.get_status`, with parsing and fallback tests.
2. Inject the three timeout settings in `Settings` and `main.py`, keeping the old environment variables working by default.
3. Rewrite the two `_expire_*` helpers in `eval_poller`: the execution budget uses `status.started_at`, the queue budget uses `eval_started_at`, and the budget is selected by kind.
4. Add `startedAt`, `elapsedSeconds`, `queueSeconds` and `progressPercent` to `eval_polled` / `eval_timeout` events.
5. Add the unit tests listed above and run the relevant `pnpm test:api` directories.
6. Update `.env.example`, the 04 configuration table and the Agent Note; mirror the English side and run `pnpm record:i18n`.
7. After deployment, retry `01M8DEKFZ5R7` (or start a new run) and verify: a candidate may wait in the queue without being falsely killed, and test-set evaluations at the final stage receive their full budget.

## Dependencies and boundary

- Dependencies: no code dependency; validate together with [#656](https://github.com/Shadow-Azure/harness-evolution/issues/656). If #656 lands first, base this issue's test-budget change on its new final-stage submission flow; if this issue lands first, #656 can still land independently and neither reverts the other.
- The platform status contract's `started_at` is an external dependency: if a response omits it, fall back to the existing `eval_started_at`; add no HE database column and do not block the release.
- Do not change `ai-eval-platform` capacity, queueing or sharding policy in this issue, and do not change the test-set/validation-set project configuration.
- Do not change the acceptance rule in `eval_gate.py`, the `init_score/best_score/verdict` semantics or frontend fields.

## Verification

```sh
pnpm lint:api
pnpm typecheck:api
pnpm test:api -- apps/api/tests/m12-03-real-patch-eval apps/api/tests/bugfix-63-real-eval
pnpm verify:flow
pnpm test:gates
pnpm record:i18n -- .agents/notes/implemented/architecture/<agent-note>.md
```

- The new/modified poller tests pass; a fake gateway configured to queue for 3 hours and then run for 30 minutes produces no `eval_timeout`.
- Explicitly setting `HE_EVAL_TEST_TIMEOUT_SECONDS` back to 7200 still times out a test baseline that runs longer than 2 hours, proving that the per-kind budget is effective rather than a blanket increase.
- Production re-check: retry `01M8DEKFZ5R7` or a new run with the same configuration; `eval_polled` shows `startedAt`/`progressPercent`; the test baseline no longer competes with the candidate during iteration; the two test-set evaluations at the final stage complete within their budgets or end in an explainable terminal state.

## Acceptance

- A candidate that queues for 100 minutes and then actually runs for 90 minutes is not declared timed out; `eval_timeout` is recorded only after the candidate budget of actual execution time.
- The test baseline and test final use a budget independent of the candidate, and a test baseline running longer than 2 hours no longer blocks the run automatically.
- An evaluation queued longer than `HE_EVAL_QUEUE_TIMEOUT_SECONDS` still ends in an explicit queue-timeout terminal state instead of leaving the run hanging forever.
- A timeout event directly shows `kind`, `startedAt`, `elapsedSeconds` and `queueSeconds`; operators no longer have to reconstruct the timeline by hand.
- With #656 present, no test baseline is submitted at startup; the two test-set evaluations at the final stage run under the new budgets, and the gating and final score semantics are unchanged.

## Gates and CI

- Hits `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`, `pnpm test:gates`, `pnpm verify:flow` and `pnpm verify:docs`; coverage meets the repository's 80% requirement.
- Add or revise an Agent Note under `.agents/notes/implemented/architecture/`, and update its English pair and i18n record in the same PR.
- The configuration tables in `.env.example` and `plans/fullstack-design/04-backend-architecture.md` must match the defaults in `config.py`.
- Parsing of real-platform status fields needs fake contract tests; CI must not depend on the production platform.

## Non-goals

- Do not move `test_baseline` from startup to the final stage here (that is #656).
- Do not modify `ai-eval-platform` resource pools, queueing, image preparation or concurrency policy.
- Do not cache or reuse test-set baseline scores (a possible follow-up optimization).
- Do not change the candidate/baseline comparison rule, the primary metric or the `verdict` semantics.
- Do not change the frontend for this incident; progress is exposed through run events first.
