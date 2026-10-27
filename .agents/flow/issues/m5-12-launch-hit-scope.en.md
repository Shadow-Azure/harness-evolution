# Correct launch hit scope and wizard validation

English | [中文](m5-12-launch-hit-scope.md)

```yaml flow
kind: issue
id: m5-12
milestone: m5
depends:
  - m5-05
priority: P0
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 132
  url: https://github.com/Shadow-Azure/harness-evolution/issues/132
```

## Background

The m5-05 launch wizard built its hit query on `bad_cases.object_*` (the reporting object), while the design makes `probe_reports.probe_object @ object_version` the sole source of the evolution target; when the two diverge, choosing deep-research can cluster Explore's root causes. The same review found that `probes/query` does not share the launch's `defaultRef` normalization (omitting the version returns 422 while launch returns 202); the `evolution_prepare` job necessarily fails after every 202 because no handler is registered; step 2 renders a fixed four-entry legend instead of the prototype's data-driven one; the custom overlay lacks dialog semantics; and 390px layouts overflow horizontally.

## Goals

- Derive hits, statistics, and items from `probe_reports` by `probe_object @ object_version`, then backtrack to bad cases and sessions; unanalyzed and non-issue reports do not participate in evolution hits.
- Share one condition normalization across `probes/query`, `cluster-previews`, and `runs`: `defaultRef` fallback, inverted windows, unconfigured target, and zero hits behave identically.
- Stop producing a guaranteed-failing `evolution_prepare` job after 202; keep prepare as an explicit m5-06 placeholder.
- Render only non-zero legend entries; give the overlay `role="dialog"`, `aria-modal`, and Escape handling; remove horizontal overflow at 390px.
- Align 05/08/02 with the implementation.

## Design authority

- [05 §3.4/§3.5/§4.9/§4.10/§4.12](../../../plans/fullstack-design/05-api-design.md)
- [07 §5.3](../../../plans/fullstack-design/07-backend-implementation.md)
- [08 §9](../../../plans/fullstack-design/08-frontend-implementation.md)
- [02 F11](../../../plans/fullstack-design/02-features.md)

## Implementation

- Rework the `probe_query` repository to join from probes: `probe_reports → bad_case_analysis → bad_cases → session_families`; filter the window by the probe session's start and `models` by any agent model in that session tree.
- Summary: `sessions` counts distinct hit sessions, `badCases` distinct backtracked cases, `analyzed` distinct analyzed hit cases, `probes`=`usedProbes` the hit probe count, and `byAttributeType` comes from `probe_reports.attribute_type`; `unanalyzed` and `nonIssue` stay in the contract but are always 0.
- Give `ProbeQueryService` the target store so preview and launch both fall back to `default_ref`; an unconfigured target returns 409 `TARGET_NOT_CONFIGURED`.
- Register an `evolution_prepare` placeholder handler that records the preparing state and completes normally without changing the run's `preparing` intent.
- Web: keep the "unanalyzed" stat at 0, drop the wait-for-attribution note, render only non-zero distribution entries, add dialog semantics/Escape/initial focus, and make the probe table horizontally scrollable.
- Docs: rewrite 05 §3.5/§4.9, 08 §9.3, and 02 F11 to the probe scope and state that unanalyzed/non-issue reports do not participate; note the shared preview normalization in 07 §5.3.

## Implementation steps

1. Write failing tests for the probe scope, preview default version, prepare placeholder, non-zero legend, and overlay semantics
2. Rework repository/service/API and the placeholder handler, then update the web component
3. Update the design docs and the Agent Note, then run independent verification

## Dependencies and boundary

- Depends: m5-05
- Non-goals: the real six-step prepare orchestration (m5-06), the `ENGINE_INVALID` engine registry (m5-06), idempotency and run/job atomicity (not required by design), and the run-detail data source (m5-07)

## Verification

```sh
pnpm test:api -- tests/m5-05-launch-wizard
pnpm test:db
pnpm test:web
pnpm test:e2e --pattern "m5 "
pnpm contract:check
pnpm verify:docs
```

- API subset and database tests pass; all web tests pass; the launch wizard and run-list E2E pass; contracts show no drift; documentation gates pass.

## Acceptance

- With data where reporter A and root cause B diverge, querying B hits while querying A does not (or only yields 0 unanalyzed).
- Omitting `targetVersion` resolves to `defaultRef` for both preview and launch.
- Launch no longer leaves a job failed with "no handler registered"; the run stays `preparing`.
- Step 2 shows only attribute types that actually hit; 390px has no horizontal scroll; Escape closes the wizard.

## Gates and CI

- `contract:check`, `verify:web-style`, `verify:docs`, `verify:flow`, E2E, and coverage gates

## Non-goals

- Do not backfill attribution for unanalyzed reports (the external system owns it; V1 exposes no analysis trigger)
- Do not change the run state machine or the six-step endpoint shapes
