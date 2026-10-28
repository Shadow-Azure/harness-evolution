# Split build-and-docs pipeline into concurrent lanes

English | [中文](m6-ci-lane-split.md)

```yaml flow
kind: issue
id: m6-09
milestone: m6
depends: []
priority: P1
status: done
scope:
  - .github/workflows/ci.yml
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 156
  url: https://github.com/Shadow-Azure/harness-evolution/issues/156
```

## Background

The CI workflow `.github/workflows/ci.yml` serializes static checks, unit tests, database tests, integration, E2E, build, bundle gate, and docs gate inside one job `build-and-docs` (19 steps, timeout 20 minutes), so CI wall time equals the sum of every step. Script-level inspection confirms that, except `verify:bundle` hard-depending on `pnpm build` artifacts, the steps are mutually independent — E2E spawns its own `run-api.mjs start` + `vite` child processes and needs no build output, API steps only need the Python venv, and everything else only needs `pnpm install`. The serialization is a historical accretion (docs gates were embedded later), not a dependency constraint.

## Goals

- Split `build-and-docs` into environment-grouped concurrent lane jobs so CI wall time shrinks substantially (key path expected to drop by half or more).
- Every run still executes every gate with no path filtering, preserving the "no bypass for code or docs" principle.
- Add a `ci-ok` aggregate job as the single required check for branch protection; `mysql`/`flow-online` being skipped by `if` must not fail it.

## Design authority

- [plans/fullstack-design/09-review-guide.md](../../../plans/fullstack-design/09-review-guide.md) R5/R8: contract drift guard (`contract:check`) and dual-database CI (SQLite/MySQL) are gates that must run on every execution; splitting may only change execution topology, never drop gates.
- [plans/fullstack-design/01-architecture.md](../../../plans/fullstack-design/01-architecture.md) "契约防漂移" row: CI verifies "regenerate = no diff", which grounds placing `contract:check` in the `api-static` lane.
- Where implementation conflicts with the linked sections, the linked sections win; this issue only changes execution topology and no gate content or threshold.

## Implementation

- Split the `build-and-docs` job in `ci.yml` into seven concurrent lanes: `web-static` (lint:web + typecheck:web + verify:web-style), `api-static` (lint:api + typecheck:api + contract:check), `unit-tests` (test:web + test:api, keeping the ≥80% coverage verdict in one job), `db-sqlite` (test:db + fixtures smoke + verify:local-data), `e2e` (test:integration + test:e2e), `build-lane` (build → verify:bundle + typecheck), `docs-flow` (verify:docs + test:gates + verify-flow --diff).
- Add a `ci-ok` aggregate job: `needs` every lane, runs with `if: always()` and fails only on `failure`/`cancelled`, letting `skipped` pass (covering `flow-online`'s PR-only condition and push events).
- `mysql` and `flow-online` stay unchanged; top-level `concurrency` and `permissions` stay unchanged.

## Implementation steps

1. Rewrite the jobs in `ci.yml` per the grouping above; each lane carries its own checkout plus pnpm/pip setup (shared caches).
2. Append the `ci-ok` aggregate job using the `needs.*.result` array expression to detect failure/cancellation.
3. Validate locally with YAML parsing plus expression review, `pnpm test:gates`, and `pnpm verify:flow`.

## Dependencies and boundary

- Dependencies: none.
- Boundary: only `.github/workflows/ci.yml`, flow files, and Agent Notes change; the branch protection switch (required check from `build-and-docs` to `ci-ok`) is a repo-settings operation done around PR merge, not part of this diff.
- Non-goals: no path filtering; no coverage-merge split (`unit-tests` stays one job); no E2E per-file sharding; no changes to gate script contents.

## Verification

```sh
pnpm verify:flow && pnpm test:gates && pnpm lint:docs
```

- All three commands exit 0 with no new red gates.

```sh
node -e "const yaml=require('./node_modules/.pnpm/node_modules/yaml/dist/index.js');const fs=require('fs');const d=yaml.parseDocument(fs.readFileSync('.github/workflows/ci.yml','utf8'));console.log(Object.keys(d.toJS().jobs).join(','))"
```

- Output contains `web-static,api-static,unit-tests,db-sqlite,e2e,build-lane,docs-flow,mysql,flow-online,ci-ok` and the YAML parses.

## Acceptance

- Every step of the old `build-and-docs` is found in some lane in `ci.yml`; no gate is dropped or weakened.
- `ci-ok` fails when any lane fails and still passes when `flow-online` is skipped (push events).
- `pnpm verify:flow` and `pnpm test:gates` stay green; commit and PR titles carry `(#N)`.

## Gates and CI

- `pnpm verify:flow` / `verify-flow --diff`: issue eligibility and scope coverage (diff stays inside scope globs).
- `pnpm test:gates`: gate self-tests stay green (no gate script changes).
- GitHub Actions runtime cannot execute locally; first-run validation relies on real CI triggered by the PR, and `ci-ok` semantics follow the official GitHub Actions semantics of `needs.*.result`.

## Non-goals

- No path filtering or merge-queue tuning.
- No coverage artifact merging or cross-job coverage aggregation.
- No E2E serialization changes (`--test-concurrency=1` stays; sharding is a separate issue).
