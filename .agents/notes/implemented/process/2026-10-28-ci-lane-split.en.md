# Agent Note: CI split into concurrent lanes with a ci-ok aggregate gate

Status: implemented

English | [中文](2026-10-28-ci-lane-split.md)

## Problem

`ci.yml` serialized static checks, unit tests, database tests, integration, E2E, build, bundle, and docs gates inside one job `build-and-docs`, so CI wall time was the sum of all steps (timeout 20 minutes). Step-by-step script inspection confirmed that, except `verify:bundle` hard-depending on `pnpm build` artifacts, the steps are mutually independent — E2E spawns its own `run-api.mjs` + `vite` children and needs no build output, API steps only need the Python venv, and everything else only needs `pnpm install`. The serialization came from docs gates being embedded later, not from dependency constraints.

## Decision

- Split `build-and-docs` into seven concurrent lanes by environment: `web-static`, `api-static`, `unit-tests`, `db-sqlite`, `e2e`, `build-lane`, `docs-flow`; `mysql` and `flow-online` stay as they were. Each lane carries its own checkout and pnpm/pip setup with shared caches.
- The only real artifact dependency (build → verify:bundle) serializes inside `build-lane`; the ≥80% coverage verdict stays within the single `unit-tests` job with no cross-job coverage aggregation.
- Add a `ci-ok` aggregate job: `needs` every lane with `if: always()`, vetoing only `failure`/`cancelled` via the `needs.*.result` expression and letting `skipped` pass — covering `flow-online`'s PR-only condition being skipped on push events. Branch protection's required check moves to the single `ci-ok` point; adding or removing lanes later only touches the `needs` list.
- Every run still executes every gate with no path filtering; the "no bypass for code or docs" principle is unchanged.

## Alternatives considered

- Path filters (skip e2e/build lanes for docs-only PRs): bigger payoff, but violates the repo's explicit no-bypass principle by letting docs PRs dodge gates; rejected.
- Splitting `unit-tests` into web/api jobs: one more parallel slice, but the 80% coverage threshold becomes a cross-job aggregation problem requiring a coverage-artifact merge facility; the complexity is not worth it; rejected.
- Keeping one job and only raising the timeout: does not address wall time; rejected.
- Sharding E2E per file across jobs: `m3-session-browser` alone is the big single chunk, but sharding changes `--test-concurrency=1` semantics and needs artifact merging; evaluate in a separate issue.

## Consequences

- The CI key path drops from "sum of all steps" to "longest lane plus one aggregate"; each lane pays an extra ~1–2 minutes of setup, with a net gain expected above half.
- Branch protection needs a one-time switch of the required check from `build-and-docs` to `ci-ok` (a repo-settings operation done around PR merge); a missed switch leaves the old check name pending forever.
- `ci-ok` correctness relies on GitHub Actions' `needs.*.result` semantics; locally only YAML parsing and expression review are possible, and the first real run is the final validation.
- Lane failure triage moves from one log to per-job logs; the `case` output line `lane results:` prints each lane's result for locating failures.
