# PR pipeline takes 18–20 minutes: why unit-tests runs 1,724 API tests serially and how to parallelize

English | [中文](bugfix-ci-unit-tests-duration.md)

```yaml flow
kind: issue
id: bugfix-07
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - .github/workflows/**
  - apps/api/pyproject.toml
  - apps/api/tests/**
  - scripts/run-api.mjs
  - scripts/gates.spec.mjs
  - package.json
  - pnpm-lock.yaml
  - apps/web/vitest.config.ts
  - docs/**
  - plans/**
  - .agents/**
  - AGENTS.md
adr: []
github:
  number: 445
  url: https://github.com/Shadow-Azure/harness-evolution/issues/445
```

## Background

### Problem scenario

Before PR #432 merged on 2026-11-20, CI ([run 44693742962](https://github.com/Shadow-Azure/harness-evolution/actions/runs/44693742962)) took 18 minutes 10 seconds from workflow trigger to `ci-ok`, and `unit-tests` accounted for 18 minutes 01 seconds of it; the same run's `e2e` took 8:14, `docs-flow` took 2:21, and every other lane finished within two minutes. `ci-ok` is the only required branch-protection check and waits for all lanes, so the mergeable time of a PR is set by the longest `unit-tests`, not by the actual work of the whole gate set.

Two other successful runs in the same period took 20:39 and 19:45; the last eight successful runs that day had `unit-tests` between 13 and 21 minutes. During that long feedback window new pushes also trigger `cancel-in-progress`: eight runs between 06:16 and 07:47 were cancelled after 4–14 minutes, burning runner time again.

| Run | Event | unit-tests | Next longest lane | CI wall time |
|---|---|---:|---:|---:|
| 44693742962 | Before PR #432 merged | 18:01 | 8:14 (e2e) | 18:10 |
| 44693782397 | Same-branch rerun | 20:39 | 6:41 (e2e) | 21:07 |
| 44690928979 | main push | 19:45 | 6:50 (e2e) | 19:54 |

### Time breakdown

Based on the `unit-tests` job log of run 44693742962, the 18 minutes 01 seconds breaks down as follows:

| Phase | Log time | Duration | Share of job |
|---|---|---:|---:|
| checkout + pnpm install + Python venv | 07:16:26–07:16:54 | 28s | 2.6% |
| Web vitest (101 files / 766 tests) | 07:16:55–07:17:42 | 47s | 4.3% |
| API pytest + coverage (1,724 passed / 22 skipped) | 07:17:42–07:34:24 | 16:37 | 92.2% |
| Coverage report and job teardown | 07:34:25–07:34:27 | <1s | <0.1% |

- Web tests already run in parallel: vitest uses its default worker pool and finishes 766 tests in 47 seconds, so it is not the bottleneck.
- API tests run serially in one process: `pnpm test` → `test:api` → [`scripts/run-api.mjs`](https://github.com/Shadow-Azure/harness-evolution/blob/main/scripts/run-api.mjs#L32-L34) → `pytest.main([])`, with no `-n` or xdist; 1,724 tests in one process at 996.87 seconds means 0.58 seconds per test on average.
- A standard GitHub-hosted Ubuntu runner has 4 vCPU, so the API phase uses one core and leaves three idle; on a local 10-core machine the same suite takes 321.0 seconds serially (0.19 seconds per test), 117.6 seconds on the first `-n 4` run (2.7×), and 129–165 seconds across repeat runs, confirming that parallelism is an available lever but the timing tests must be fixed first.

### Why serial execution grows to 18 minutes

1. **No concurrency in the process**: pytest runs one test at a time, and `pnpm test` chains web and api with `&&`, so the 47-second web run starts only after the API run ends and the two suites add up on the critical path instead of overlapping.
2. **Many tests rebuild the app and rerun all migrations**: tests contain 132 `create_app` calls and 120 `upgrade_database` calls; [`create_app`'s lifespan](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/api/app/main.py#L465-L485) runs all 24 Alembic revisions every time. A fresh local SQLite upgrade takes 0.51 seconds, so hundreds of test database builds accumulate into minutes of fixed cost.
3. **Password hashing repeats at production cost**: [`IdentityService`](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/api/app/service/identity/service.py#L30) and [`PasswordProvider`](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/api/app/service/identity/password.py#L19-L20) construct a `PasswordHasher` and compute a dummy hash per instance; the 132 `create_app` call sites repeat that cost at about 42 ms locally. Production parameters cannot be lowered, but tests can inject a cheap hasher.
4. **The unit lane includes real processes and real waits**: [`test_git_workspace.py`](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/api/tests/m5-09-git-candidate/test_git_workspace.py#L1085) starts real git subprocesses and sleeps for 4.5 seconds, `m12-03` runs real patch/eval, `m12-01` starts an HTTP upstream; 33 fixture sites rebuild the corpus or external tables, and one run emits 3,691 warnings. The slowest 40 tests total about 53 seconds locally, so the other ~83% is distributed startup, migration and teardown cost.
5. **The same database tests run twice**: the 33 tests in `tests/test_database.py` run both in `unit-tests` and in the `db-sqlite` lane; the latter finishes in 51 seconds, so the copy inside the unit lane adds no coverage value.
6. **The timeout and feedback window hide regressions**: `unit-tests` allows 30 minutes, so 18–20 minutes looks "normal"; without a `--durations` summary, a newly added slow test is invisible in CI and only pushes the wall clock higher.

Conclusion: the main causes are the lack of concurrency in the API suite and the high fixed startup cost per test, not a few slow files; splitting web out saves only 47 seconds and is not enough by itself.

## Goals

- On a standard 4 vCPU runner, cut `unit-tests` from 18–20 minutes to ≤8 minutes and full CI to ≤10 minutes.
- Keep the complete suite: all 1,724 API tests, 766 Web tests and 22 skips remain, with no path filters and no skipped lanes.
- Keep coverage semantics: API ≥90% (branch), Web ≥80% (branches/functions/lines/statements).
- Stay stable for three consecutive PR runs with p95 `unit-tests` ≤8 minutes; any isolation flake must be locatable and reproducible on its own.
- Make the CI summary separate setup, web and api time and list the slowest tests so later regressions stay visible.

## Design authority

- [AGENTS.md development flow](https://github.com/Shadow-Azure/harness-evolution/blob/main/AGENTS.md#L67): behavior changes ship with unit and cross-stack tests, CI must execute tests, and coverage must stay at or above 80%.
- [03 frontend test running](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/03-frontend-architecture.md#L290): `pnpm test` runs everything and CI and local share one `vitest.config.ts`; splitting jobs must not change the test set or configuration.
- [04 database and CI](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/04-backend-architecture.md#L195): SQLite fast runs and MySQL `-m mysql` integration tests stay on two paths; the existing lane split is preserved.
- [09 R8 cross-dialect differences](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/09-review-guide.md#L138): dual-database CI is an established gate, so `db-sqlite` and `mysql` lanes are neither merged nor skipped.
- [run-api.mjs coverage wrapper](https://github.com/Shadow-Azure/harness-evolution/blob/main/scripts/run-api.mjs#L32-L34): coverage starts and stops inside the pytest main process, while xdist workers live in other processes; adding `-n` directly would undercount coverage, so collection must switch to a mergeable method.
- [2026-10-28 CI lane split Agent Note](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/process/2026-10-28-ci-lane-split.md): it rejected a web/api split because it assumed cross-job coverage aggregation, but the [Web threshold of 80](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/web/vitest.config.ts#L12-L17) and [API threshold of 90](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/api/pyproject.toml#L41-L45) are already judged per suite; the split needs no aggregation, and the old rationale should be corrected with this issue's evidence.
- [ci.yml unit-tests job](https://github.com/Shadow-Azure/harness-evolution/blob/main/.github/workflows/ci.yml#L44-L66): one job installs both Node and Python, runs web+api serially and allows 30 minutes; that job is the physical location of the current critical path.

## Implementation

- Split `unit-tests` into `unit-tests-web` and `unit-tests-api` jobs that run in parallel; both join `ci-ok`'s `needs`, either failure still vetoes, and web leaves the API critical path.
- Add `pytest-xdist` and `pytest-cov` to the dev dependencies in `apps/api/pyproject.toml`; CI uses an explicit `-n 4` (4 vCPU standard runner), local may use `-n auto`, and `test:api:serial` stays as an escape hatch for isolation debugging.
- Replace the hand-written coverage wrapper in `run-api.mjs` with pytest-cov: `--cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90`; pytest-cov merges xdist worker data automatically and the threshold stays 90%.
- Harden timing-sensitive tests before enabling parallelism: `test_git_timeout_terminates_the_process_group_before_returning` failed once under `--dist loadscope` and once under the default distribution because `process-started` was never created; replace the fixed `sleep(4.5)` and 2-second timeout with event waits or polling, and mark tests that truly need real processes for a serial phase.
- Use `--dist load` as the default distribution and verify module-level state first; if a module must stay on one worker, use `--dist loadscope` and add isolation per module instead of falling back to global serial execution.
- Phase 2 lowers fixed cost per test: use a session-scoped template database (migrate once, copy the file per test) or a `create_app(run_migrations=False)` test seam to avoid 120 repeated Alembic upgrades.
- Phase 2 injects a cheap `PasswordHasher` (test-only configuration, production defaults unchanged) and avoids recomputing the dummy hash on every construction.
- Emit `--durations=25` in CI and write setup/web/api time into the job summary; start as visibility and a soft warning, then tighten once stable.

## Implementation steps

1. Record baseline: serial `pytest -q`, `-n 4`, and `--durations=25` wall times, pass/skip counts and coverage, and capture them in the PR description.
2. Add pytest-xdist and pytest-cov and run `-n 4` three times locally, confirming pass/skip counts and coverage match the serial run.
3. Fix timing/isolation problems exposed by parallelism, covering at least the reproduced git timeout test; mark tests that cannot run in parallel and move them to a serial catch-up phase.
4. Change `ci.yml` to split web/api jobs, wire them into `ci-ok`, run API with `-n 4`, keep the existing timeout semantics and set a reasonable per-job limit.
5. Observe three real CI runs on the PR and record `unit-tests` and full CI wall time; adjust `-n`, `--dist` or job limits from the results.
6. If the ≤8 minute target is still missed, execute the Phase 2 template database and cheap hasher; update docs and gates, and write the measured data back into this issue.

## Dependencies and boundary

- Dependencies: a standard 4 vCPU GitHub-hosted runner and PyPI access for `pytest-xdist`/`pytest-cov`; no new service, database or external credential is needed.
- Boundary: only CI and test infrastructure change; application behavior, production hash parameters and database schema stay unchanged; no existing test is deleted or skipped.
- Coordination: if xdist isolation cannot be stabilized with reasonable effort, the fallback is cross-runner sharding by suite, which needs coverage artifact merging and multiplies CI minutes, so it must be evaluated separately rather than used as this issue's first choice.

## Verification

```sh
cd apps/api
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q -n 4 --durations=25
cd ../..
pnpm test
pnpm verify:flow
pnpm verify:docs
```

| Mode | Command | Wall time | Result |
|---|---|---:|---|
| Serial baseline | `pytest -q` | 321.0s | 1,724 passed / 22 skipped |
| 4-worker default distribution | `pytest -q -n 4` | 117.6–165.1s | 3 of 4 runs green, 1 timing flake |
| 4-worker loadscope | `pytest -q -n 4 --dist loadscope` | 141.1s | 1 timing flake |

- The local machine is a 10-core macOS host with Python 3.12.14, pytest 8.4.2 and xdist 3.8.0; three consecutive `-n 4` runs took 151.1s, 165.1s and 129.4s, and the second failed on the same git timeout test, so hardening that test is a prerequisite for parallelization. Those numbers are only for relative comparison, and CI is judged by three real runs on 4 vCPU.
- After parallelization the pass/skip counts must match the serial run, and API coverage must stay ≥90% and Web ≥80%; failing either means the work is incomplete.
- CI expectation is API dropping from 16:37 to 6–8 minutes and the `unit-tests` job reaching ≤8 minutes; if any of three runs exceeds 8 minutes, adjust `-n`/distribution or execute Phase 2 rather than relaxing the bar.

## Acceptance

- Three consecutive PR runs finish `unit-tests` in ≤8 minutes and full CI in ≤10 minutes, and `ci-ok` still aggregates both new jobs correctly.
- The API suite keeps 1,724 passed / 22 skipped and Web keeps 766 passed / 1 skipped; API coverage ≥90% and Web ≥80%.
- The reproduced git timeout test passes three consecutive `-n 4` runs; no new isolation flake appears.
- The CI summary includes setup/web/api time and `--durations=25`; the PR description carries a before/after table, run IDs and the commands actually executed.
- If Phase 2 is deferred, the issue stays open and records the remaining cost and bottleneck instead of treating the first milestone as full completion.

## Gates and CI

- Run at least `pnpm test`, `pnpm verify:flow`, `pnpm verify:docs` and `pnpm test:gates` locally; workflow changes need manual review of job dependencies and timeouts.
- The PR title and every commit title carry `(#N)`; `verify-flow --diff` checks that this issue's scope covers every changed file.
- Branch protection still points only at `ci-ok`; both new jobs must be in `needs`, and unit-tests must not be removed from the aggregate gate.

## Non-goals

- Do not delete, skip or weaken any test, add path filters, or lower coverage thresholds.
- Do not change production password hash parameters, application runtime behavior or database schema.
- Do not make cross-runner sharding the first choice or introduce artifact-merging infrastructure for it.
- Do not fix unrelated flaky tests or refactor application code along the way.
