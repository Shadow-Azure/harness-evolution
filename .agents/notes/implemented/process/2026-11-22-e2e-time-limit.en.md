# Agent Note: The real-browser E2E time limit follows measured runner behaviour

Status: implemented

English | [中文](2026-11-22-e2e-time-limit.md)

## Problem

The real-browser E2E suite (79 cases, M1–M8) has a 10-minute internal ceiling in `scripts/run-e2e.mjs`. A healthy run takes about 8 minutes locally, but shared GitHub runners measured 8–13 minutes: on 2026-11-22 several runs were killed at 600 seconds (exit 124) while `pnpm test:e2e` passed locally on the same commit. The failure message is "suite exceeded its time limit", not a failing case, so maintainers can only rerun repeatedly — wasting CI time and eroding what a red CI tells you.

## Decision

- Raise the internal ceiling in `scripts/run-e2e.mjs` from 600 to 900 seconds (`HE_E2E_TIMEOUT_MS` default) while keeping it environment-overridable.
- Raise the CI e2e step limit from 12 to 18 minutes and the job limit from 15 to 25 minutes, leaving a 3-minute and a 10-minute margin over the suite budget.
- The ceiling stays a hard gate: a genuine hang is still killed at 15 minutes and returns 124, so a performance regression cannot masquerade as a pass — it only separates "slow runner" from "failing case".
- The suite stays serial with its existing performance assertions; this decision changes only the time budget, not the tests.

## Alternatives considered

- **Keep 10 minutes and rerun on failure**: it does eventually pass, but each rerun costs 10+ minutes and treats a slow runner as a random event; maintainers cannot tell a flake from a regression from the failure message.
- **Disable e2e or path-filter it**: loses the real-browser M1–M8 coverage and conflicts with the repository rule that CI must execute tests.
- **Parallelise the browser cases**: it would cut wall-clock time but requires reworking the shared browser/port harness; risk and effort far exceed adjusting the budget, so it stays a follow-up performance item.

## Consequences

- A genuine E2E hang is noticed up to 5 minutes later (10 → 15 minutes), an acceptable delay in diagnosis.
- Slow shared-runner starts are no longer recorded as failures; the failure signal returns to "a case assertion failed".
- If the suite keeps growing and a healthy run approaches 15 minutes, parallelise or split the lane instead of raising the ceiling again.
