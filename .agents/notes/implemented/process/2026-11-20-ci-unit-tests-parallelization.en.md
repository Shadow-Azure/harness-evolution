# Agent Note: split CI unit tests by suite and run the API suite under xdist

Status: implemented

English | [中文](2026-11-20-ci-unit-tests-parallelization.md)

## Problem

`unit-tests` ran Web and API serially in one job: Web vitest covered 101 files / 767 cases in about 47 seconds, while API pytest ran 1,739 cases on a 4 vCPU runner in 16 minutes 37 seconds — an 18 minute 01 second job. `ci-ok` waits for every lane, so the PR merge time was set by this longest lane. The API suite was single-process, and `pnpm test` joined both suites with `&&`; coverage was started and stopped by hand inside `run-api.mjs`, and xdist workers live outside that process, so adding `-n` alone would lose their coverage. Parallelism also exposed a timing-sensitive case: `test_git_timeout_terminates_the_process_group_before_returning` relied on a 2 second timeout plus a fixed `sleep(4.5)` and failed on a loaded worker when the script had not started before the timeout. CI also lacked per-phase timings and a slowest-cases summary, so regressions stayed invisible.

## Decision

- Split `unit-tests` in `ci.yml` into two parallel jobs, `unit-tests-web` and `unit-tests-api`, both listed in `ci-ok.needs`; Web gets a 10 minute timeout and API 15 minutes, and a failure in either still vetoes the run.
- Add `pytest-xdist` and `pytest-cov` to the dev dependencies in `apps/api/pyproject.toml`. `pnpm test:api` defaults to `-n auto` (local cores), CI passes an explicit `-n 6` (tuned on a 4 vCPU runner: `-n 4` jobs jittered between 7m58s and 8m31s), and `pnpm test:api:serial` keeps a serial entry point for isolation and timing work; `--serial` makes a single `test:api` run serial.
- Move coverage to pytest-cov: `--cov=app --cov-branch --cov-report=term-missing`, with `--cov-fail-under=90` added for full-suite runs; a focused path selection skips coverage (`--no-cov`) instead of judging whole-app coverage from a subset. pytest-cov merges worker data in the main process, so the API 90% branch threshold is unchanged; Web's 80% stays owned by vitest, so splitting the jobs needs no cross-job aggregation.
- Every API run passes `--durations=25` and tees the log; `unit-tests-web` and `unit-tests-api` each write setup and suite wall time to the job summary, and the API summary folds the slowest cases in. This is visibility first, not a hard threshold.
- Rewrite the timing-sensitive case around events: inject a runner that executes the script directly (no git startup), poll for `process-started`, confirm the whole process group is gone, then watch a 3 second side-effect window; the fixed `sleep(4.5)` is removed.
- Start with xdist's default `--dist load`; if module-level state requires one worker, switch to `--dist loadscope` and add isolation instead of falling back to a global serial run.

## Alternatives considered

- Keep one job and only raise the timeout: it does not fix wall time and hides regressions.
- Shard the API suite across runners: needs coverage artifact merging and multiplies CI minutes, which the issue rules out as the first choice.
- Keep the hand-written coverage wrapper: xdist workers are not in the main process, so pytest-cov is required to merge coverage.
- Skip the timing case or move it to a serial follow-up phase: it narrows parallel coverage for a case that only costs seconds; event waiting makes it stable.
- Go straight to `--dist loadscope`: less parallelism and masks module state leaks; validate the default distribution first.

## Consequences

- The API suite targets 4–8 minutes; real gains are confirmed by consecutive 4 vCPU CI runs, and Phase 2 (session-scoped template database, low-cost PasswordHasher) follows separately if the target is missed.
- Two Python test dependencies are added; `pnpm-lock.yaml` is unchanged because Python dependencies do not flow through pnpm.
- Default parallelism may expose uncleared module-level state; `test:api:serial` and failed worker logs are the entry points for locating it.
- `ci-ok` gains one more needs entry; the job count grows, but both suites run in parallel, so total runner minutes stay roughly flat.
- The API job measured 7m58s–8m31s at `-n 4`, straddling the 8-minute acceptance line; `-n 6` overlaps I/O waits, and Phase 2's template database remains the fallback if the line is still missed.
- The summary and `--durations` are soft visibility until they prove stable enough for thresholds.
