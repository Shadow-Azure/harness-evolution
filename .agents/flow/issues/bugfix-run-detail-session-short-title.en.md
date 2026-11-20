# Run detail step 2 shows short Session labels with fixed column widths

English | [中文](bugfix-run-detail-session-short-title.md)

```yaml flow
kind: issue
id: bugfix-03
milestone: bugfix
depends:
  - m21-01
priority: P2
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - .agents/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 444
  url: https://github.com/Shadow-Azure/harness-evolution/issues/444
```

## Background

Production「evolution → run detail → step 2 Session association」renders the Session's first prompt in full inside the table. For SWE-bench-style Sessions the first user message is the whole task prompt (3337 characters in this sample); at a 1500×837 CSS viewport it grows the first row to 329px and the Session column to 1247px, squeezing the other three columns to 43–79px so the association evidence cannot be checked. The V2 prototype at the same position uses a short label plus the full Session ID and keeps four columns on screen. The production/prototype comparison, quantitative evidence and root cause are in [issue #440](https://github.com/Shadow-Azure/harness-evolution/issues/440).

The root cause is a missing data field combined with an unconstrained presentation layer: association results and `session_families.short_title` already carry a short label, but the run preparation stage persists only `sessionId/title/objectTriggerAt/badCaseCount` into `stats.sessionRows` and drops `short`; the `StepSessionRow` contract has no such field. `StepSessions.vue` renders `row.title` directly, and the table uses automatic layout with wrapping cells, so a long prompt takes part in width calculation and wraps line by line. Launch wizard step 2 ([#404](https://github.com/Shadow-Azure/harness-evolution/issues/404)) was already fixed with the same「short label + full-title hover + fixed column widths」approach; run detail has not been covered.

## Goals

- Step 2 Session cells show a readable short label with a single-line ellipsis, keep the full title in a `title` hover hint, and preserve the Session ID display.
- Switch the table to fixed layout with stable widths for all four columns so `object trigger`, `bad case`, and `potential bad case` are not squeezed out by a long title at 1440/1500-wide viewports.
- Return `short` from the step API, sourced from `session_families.short_title`; for existing runs whose `stats.sessionRows` lack `short`, fall back to `title[:120]` without re-preparing historical runs.
- Keep associated Session counts, pagination, ordering, skipped and version-unknown statistics unchanged.

## Design authority

- [05 §3.6 Seven-step outputs](../../../plans/fullstack-design/05-api-design.md#36-七步产出七个独立端点): `rows[]` fields and the 4-per-page contract of `steps/sessions`.
- [08 §10.1 Run detail structure](../../../plans/fullstack-design/08-frontend-implementation.md#101-结构): table columns and display conventions of step 2 among the V2 seven steps.
- [V2 prototype](../../../plans/ui-prototype-v2/harness-evolution.html): step 2 renders `a.sess.short` plus the full Session ID and never renders the full prompt in the Session cell.
- [issue #440](https://github.com/Shadow-Azure/harness-evolution/issues/440): production reproduction, quantitative comparison and root cause.

## Implementation

- `apps/api/app/service/evolution/stages.py`: add nullable `short` to `StepSessionRow`; `_v2_session_rows` reads the persisted `short` and falls back to `title[:120]` when missing; legacy rows also get a short label.
- `apps/api/app/service/evolution/prepare.py`: write `short: session.short` while persisting `sessionRows`.
- `packages/contracts`: regenerate `openapi.json` and the generated types with `pnpm contract:generate`; never edit them by hand.
- `apps/web/src/pages/evolution/components/StepSessions.vue`: render `row.short || row.title || "未命名 Session"`, expose the full `title` through a `title` attribute, ellipsize the title to one line, and switch the table to `table-layout: fixed` with a `colgroup` that fixes the trigger and count columns.
- Tests: API tests assert `short` is persisted in `sessionRows`, returned by the step API and backfilled for historical rows; a component test uses an over-long title to assert the short label and the full hover text; an E2E test uses a real browser to assert the long title does not grow the row and all four columns stay on screen.
- Docs: add `short` to 05 §3.6 and the step 2 display convention to 08 §10.1; add an Agent Note recording the data-path and presentation trade-offs.

## Implementation steps

1. Extend `StepSessionRow` and prepare-stage persistence; add API unit tests.
2. Run `pnpm contract:generate` and commit the contract changes.
3. Rework title rendering and table layout in `StepSessions.vue`; add component tests.
4. Add an over-long prompt title to the m10-06 E2E fixture and assert row height and column widths.
5. Update the design docs and Agent Note, run the gates and a real-browser smoke test, and open the PR.

## Dependencies and boundary

- Depends on: m21-01
- Boundary: only the Session title data path, title rendering and horizontal table layout of run detail step 2. The object-appearance column, association algorithm, bad case statistics, pagination/ordering and Session ID format stay as they are.

## Verification

```sh
pnpm contract:check
apps/api/.venv/bin/python -m pytest apps/api/tests/evolution/test_m10_04_stages.py apps/api/tests/evolution/test_m10_04_prepare.py apps/api/tests/test_openapi.py
pnpm test:web -- RunDetail
pnpm test:e2e -- --pattern m10-06
pnpm test:gates && pnpm verify:docs && pnpm verify:flow
```

- `sessionRows` persists `short` and the step API returns it; rows without `short` fall back to the first 120 characters of the title.
- With an over-long prompt the Session cell stays on one line, the table does not overflow horizontally, and the other three column headers remain visible.
- The hover text equals the full `title` while the visible title is the short label.

## Acceptance

- At 1440/1500-wide viewports, run detail step 2 with an over-long prompt Session neither grows the row nor squeezes the association evidence columns.
- Short label, full-title hover hint and Session ID are all present.
- Associated Session counts, pagination, ordering, skipped and version-unknown statistics are unchanged.
- Existing runs render without being re-prepared.
- Component tests and E2E cover the over-long title regression.

## Gates and CI

- Hits `pnpm contract:check`, `pnpm lint:web`, `pnpm typecheck:web`, `pnpm test:web`, `pnpm test:api`, `pnpm test:e2e`, `pnpm test:gates`, `pnpm verify:docs`, `pnpm verify:flow`.
- The PR title and commit subjects reference this issue's GitHub number, and the PR description references product issue #440.

## Non-goals

- Do not change how `session_families.short_title` is generated or extract a semantic title.
- Do not change the association algorithm, bad case statistics, pagination/ordering or Session ID format.
- Do not add the extra「object appearance」column the prototype shows; that column-scope difference is left to a separate design decision.
- Do not commit production Session content or screenshots into the repository.
