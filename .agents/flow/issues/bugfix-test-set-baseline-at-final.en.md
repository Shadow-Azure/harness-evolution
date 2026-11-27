# Run the test-set baseline and final evaluation together at the final stage

English | [中文](bugfix-test-set-baseline-at-final.md)

```yaml flow
kind: issue
id: bugfix-70
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 656
  url: https://github.com/Shadow-Azure/harness-evolution/issues/656
```

## Backgturn

### Problem

The baseline gate (#620 / PR #622) currently submits the validation baseline and the test-set baseline in parallel when a run starts, then submits the held-out test-set final after every turn has terminated. As a result, the test-set template runs once as soon as evolution starts; each turn only uses the validation set, but the test set has already been consumed during startup.

The test set is the independent final acceptance after every problem has been iterated. Running it at startup does not fit that role and creates three concrete problems:

- The test set consumes platform capacity and budget before iteration starts; that run still happens when the run is cancelled, has no accepted turn, or fails early.
- A failed test-set baseline submission moves the run to `blocked(stage=eval)` and blocks turn 1; test-set failure is coupled to the startup path.
- The platform run list shows a test-set-template run during startup, which looks like the test set also runs during iteration.

### Current behavior

- `EvolutionAdvanceService.handle` calls `submit_baselines` before publishing turn 1; `EvolutionEvalSubmitter.submit_baselines` submits `validation_baseline` and `test_baseline` in sequence, both on `base_commit`.
- Per-turn candidates use `purpose=candidate`, and `_project_id` always resolves `validationProjectId`; `testProjectId` is only used for `test_baseline` and `test_final`, so iteration itself does not run the test set.
- `EvolutionFinalizeService.handle` calls `submit_baselines` and `submit_test_final` after all turns are terminal; `test_final` runs on the commit of the last accepted turn, falling back to `base_commit` when no turn was accepted.
- `_test_final_values` uses `test_baseline` as `init_score` and `test_final` as `best_score`; `verdict` requires an accepted turn and a final score strictly better than the test-set baseline score.
- Existing tests (for example `apps/api/tests/bugfix-63-real-eval/test_run_evaluations.py` and `apps/api/tests/m5-11-evolution-recovery/test_full_placeholder_loop.py`) treat "both baselines at startup" as the established behavior.

### Requirements

- No test-set evaluation is submitted during startup or iteration; the test set first appears in the final stage after every turn is terminal.
- The final stage submits both test-set evaluations together: the test-set baseline for the initial version (`base_commit`) and the test-set final for the evolved skill (the last accepted turn commit); when no turn was accepted, **do not fall back** to `base_commit` — create a new commit recording the run result and use it as the test-final target.
- The no-acceptance result commit records the run's terminal outcome (verdict, initial and final scores, metrics, and per-turn decisions), carries `Harness-Run-Id` and an explicit no-acceptance verdict trailer, does not change the evolved skill files, and may be an empty commit or add only a result file under `.harness-evolution/`.
- Both test-set evaluations may be in flight in parallel; only after both complete is `evolution_finals` written, with unchanged `init_score`, `best_score`, and `verdict` semantics.
- Legacy runs and retries reuse a completed test-set baseline instead of submitting it again; a missing baseline is submitted during the final stage.

## Goals

- Move `test_baseline` submission from `evolution_advance` to `evolution_finalize`, so the test set is not started before iteration ends.
- Orchestrate the test-set baseline and test-set final together in the final stage and wait for both before writing the final row.
- Keep the validation baseline, per-turn gate, and `init_score`, `best_score`, and `verdict` semantics unchanged.
- Stop the startup path from failing turn 1 because of the test-set baseline; test-set failures and retries happen only in the final stage.
- Make events, step status, and test coverage distinguish "validation only during iteration" from "two test-set evaluations in the final stage".

## Design authority

- [07 §5.8 Apply evaluation results, retries, and the final evaluation](../../../plans/fullstack-design/07-backend-implementation.md): the existing run-level evaluation, finalization, and retry path; this issue changes when the test-set baseline is submitted.
- [14 §2 Terms and semantics](../../../plans/fullstack-design/14-target-project-ids.md): the validation set drives per-turn candidate decisions and the test set provides independent final acceptance; this issue makes the test set appear only in final acceptance.
- [Agent Note: SkillOpt-style baseline gate and test-set final](../../../.agents/notes/implemented/architecture/2026-11-25-baseline-gate-test-final.en.md): records the current "both baselines at startup" behavior and rationale; this issue changes the test-set baseline timing and must update the note and its English side.
- [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt): compares the initial and final versions on the held-out test set at the end; this issue keeps the comparison but moves both evaluations after iteration.
- [05 §4.11 Evolution target configuration](../../../plans/fullstack-design/05-api-design.md) and [06 §5.2 evolution_runs](../../../plans/fullstack-design/06-database-design.md): test-set template ID configuration and snapshot; this issue adds no fields.

## Implementation

### Overview

```text
run start / advance
  └─ validation_baseline only (base_commit)
turns ...
finalize (all turns terminal)
  ├─ test_baseline (base_commit)      ─┐
  └─ test_final   (accepted / result commit)    ─┴─ wait both → evolution_finals
```

- `EvolutionEvalSubmitter`:
  - The startup entry submits only the validation baseline (for example `submit_validation_baseline`) and no longer submits `test_baseline`.
  - A new final-stage entry (for example `submit_test_evaluations`) submits `test_baseline` and `test_final` together, reusing the idempotent `ensure_run_evaluation` logic.
- `EvolutionAdvanceService.handle`: submits only the validation baseline and no longer triggers `test_baseline`.
- `EvolutionFinalizeService.handle`: after all turns are terminal, ensures the validation baseline (legacy-run compatibility); when a turn was accepted it uses the last accepted commit for `test_final`; when no turn was accepted it first creates and pushes a result commit (below), then submits the test-set baseline and `test_final`; if either is incomplete it returns unfinished and does not write `evolution_finals`.
- No-acceptance result commit: create a commit on the run branch that records the run's terminal outcome (an empty commit or one that adds only a `.harness-evolution/` result file), with `Harness-Run-Id`, `Harness-Verdict: no-acceptance`, and the verdict, scores, metrics, and per-turn decisions in the message. It must not change skill files, so its tree differs from the accepted-skill path while the evaluated skill remains the initial version; retries reuse the same commit instead of creating another; the commit must be readable by the platform before `test_final` is submitted (push the run branch or the commit first).
- `EvolutionEvalPoller`:
  - The finalize follow-up re-enqueue condition checks both `test_baseline` and `test_final` instead of only `test_final`; finalize is enqueued only after both complete.
  - The polling path continues to update the row matching each `kind`; failures still go to `blocked(stage=eval)`.
- `retry.py`: when `/retry` clears a failed test-set baseline or final row, it resubmits through the existing `reset_run_eval_for_retry`; a completed baseline is not reset.
- Events and frontend: startup and iteration events no longer show a test-set baseline submission; the final step shows both the test-set baseline and final evaluations plus the final comparison. If the frontend still renders only the final row, at minimum the step status must wait for both evaluations and the copy must distinguish the test-set baseline from the test-set final.

### Compatibility and boundaries

- Legacy runs: reuse a `test_baseline` that already exists and is completed; submit it during finalization when it is missing or pending.
- Legacy runs with an existing `test_final`: keep the current idempotent behavior and do not re-run a completed final.
- A run cancelled or failed before finalization submits no test-set evaluation.
- If the test-set template is unavailable or a submission fails, the final stage enters `blocked(stage=eval)` with an error that distinguishes `test_baseline` from `test_final`; turn 1 and completed iterations are unaffected.
- Do not change the `validation_baseline` submission timing, gate logic, or candidate acceptance rules.
- Do not change `test_baseline` commit selection (`base_commit`); `test_final` still uses the last accepted commit when a turn was accepted, and switches to the result commit when no turn was accepted instead of falling back to `base_commit`.

## Implementation steps

1. Split the submission entry points: startup submits only the validation baseline; add the two test-set submissions for the final stage.
2. Adjust `advance`, `finalize`, and the poller enqueue/wait conditions so the final row is written only after both test-set evaluations complete.
3. Implement the no-acceptance result commit: creation, idempotent reuse, and pushing it before submitting `test_final`; confirm it does not change skill files.
4. Update `retry`, failure, and event copy; confirm idempotent reuse for legacy runs and completed evaluations.
5. Update the frontend final-step status and copy if needed, keeping the `initScore` and `bestScore` fields unchanged.
6. Update design docs, the Agent Note, and tests: remove the "both baselines at startup" and "no acceptance falls back to base_commit" assertions and add coverage for "no testProjectId before finalization", "two test-set submissions in parallel at finalization", "no-acceptance creates a result commit used as the final target", and "both must complete before finals are written".

## Dependencies and boundary

- Dependencies: the baseline gate and run-level evaluation implementation merged in PR #622; `testProjectId` configuration and snapshot already exist.
- Not dependent on the final acceptance state of #620; this issue changes only the test-set evaluation timing.
- Delivery boundary: code, tests, frontend step status, design docs, and the Agent Note; no evaluation platform, template, or external contract changes.
- Non-goals: do not cancel the test-set final, change the verdict rule, or change the initial-versus-final comparison semantics.

## Verification

```sh
pnpm test:api -- -k "baseline or finalize or run_evaluation"
pnpm verify:flow
pnpm lint:docs
pnpm verify:docs
```

- Data: the run-level evaluation tests in `bugfix-63-real-eval`, the full placeholder loop in `m5-11-evolution-recovery`, and the fake and real gateway stubs.
- Expected:
  - No `testProjectId` submission occurs during startup or iteration; the test-set template launch count is 0.
  - After all turns are terminal, the final stage submits one test-set evaluation for `base_commit` and one for the final commit; with an accepted turn the final commit is the last accepted one, without an accepted turn it is the new result commit, and both may be in flight in parallel.
  - A no-acceptance run creates exactly one result commit and `test_final` targets it rather than `base_commit`; the result commit records verdict, scores, metrics, and per-turn decisions without changing skill files; retries do not create duplicates.
  - `evolution_finals` is written only after both complete; `init_score`, `best_score`, and `verdict` match current behavior.
  - A simulated test-set baseline failure moves the run to `blocked(stage=eval)` without affecting turn 1 or validated turns; `/retry` resubmits only the failed item.
  - A legacy run with a completed `test_baseline` is not resubmitted.

## Acceptance

- The startup and iteration paths no longer submit `test_baseline`; the test-set template is never called before finalization.
- The final stage has both `test_baseline` and `test_final`, on `base_commit` and the final commit respectively (the last accepted commit, or the result commit when no turn was accepted), and writes finals only after both complete.
- `evolution_finals` keeps the same `init_score`, `best_score`, and `verdict` semantics, and the frontend final step can distinguish the two evaluations.
- Legacy runs, failed retries, and runs with no accepted turn (the result commit is created and the final target is not `base_commit`) are covered by tests.
- The relevant tests, flow, docs, and bilingual pairing gates pass.

## Gates and CI

- Hit: `pnpm test:api`, `pnpm test:gates`, `pnpm verify:flow`, `pnpm verify:flow-online`, `pnpm lint:docs`, `pnpm verify:docs`, `pnpm typecheck:api`, `pnpm lint:api`.
- If the frontend changes: `pnpm test:web`, `pnpm typecheck:web`, `pnpm lint:web`, `pnpm verify:web-style`.
- No new gate scripts.

## Non-goals

- Do not change the validation baseline or the per-turn gate; do not change the strict-improvement `verdict` rule.
- Do not cancel the test-set final or reduce the test set to a single run; the initial and final versions are each evaluated on the test set once.
- Do not change the evaluation platform contract, templates, or service token; do not change target configuration fields.
- Do not redesign unrelated baseline or final-evaluation UI.
