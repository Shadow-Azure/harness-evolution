# Launch wizard: always-clickable next with inline required-field validation and empty-hit state

English | [中文](m6-wizard-validation-empty-state.md)

```yaml flow
kind: issue
id: m6-11
milestone: m6
depends:
  - m5-05
priority: P1
status: ready
scope:
  - apps/web/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 161
  url: https://github.com/Shadow-Azure/harness-evolution/issues/161
```

## Background

### What the problem is

Wizard step 1 of 「启动自进化」 concentrates all validation into the disabled state of the "下一步：查询匹配报告" (Next: query matching reports) button: `LaunchWizard.vue` disables it outright with `:disabled="!selectedTarget || !targetVersion || windowInvalid()"`, giving users no explanation of why it cannot be clicked; meanwhile the time range is labeled required (`*`) but does not participate in the disabled condition, producing an inconsistent "sometimes gray, sometimes clickable" experience. When the form is complete but the query hits zero probes, the backend `probes/query` returns `409 NO_PROBES_MATCHED`, and the frontend renders the raw English message at the bottom of step 1, terminating the flow there.

### Symptoms

- With no target or version selected the "Next" button is grayed out with no explanation on click; with the time range empty the button is clickable anyway, so the required `*` marker contradicts the disable rule.
- With target, version, and time range all filled but zero hits, step 1 shows a red English line "no analyzed probe matches the wizard condition"; the wizard cannot reach step 2 and offers no "adjust the condition" guidance.
- The unit test `LaunchWizard.test.ts` asserts the button's `disabled` attribute directly (initial no-target, inverted range, and other scenarios), cementing the disabled state as expected behavior.

### Impact

- Users get no pointer to what must be filled in on an empty form; required-field feedback relies on guessing, hurting step 1 usability.
- Zero hits become an error terminal: users see an internal English message and stay on step 1, which mismatches the real semantics of "the query succeeded but returned nothing".

### Root cause

- `runQuery()` silently `return`s on `!selectedTarget || windowInvalid()` with no per-field feedback channel; the button's disabled state is the only validation expression.
- The prototype `harness-evolution.html` never had a disabled `wz-query` button; the app diverged when it added one.
- The frontend treats `409 NO_PROBES_MATCHED` like any other error and dumps it into `previewError`, never translating it into a "result is empty" business empty state; the current wording of `05-api-design.md §4.9` ("the frontend stays on step 1") cements that behavior too.

### Suggestion

- Keep "Next" always clickable; run field-level required validation on click: when target, version, or either end of the time range is missing, mark that input red and show a red "missing required field" hint below it; reuse the existing copy for an inverted range and mark it red too; clear each field's error as soon as the field changes.
- Treat zero hits as a successful query with an empty result: advance to step 2 and render an empty state (no matching problem reports/probes plus adjust-the-condition guidance), with both exit buttons disabled; other errors keep the current step-1 display.
- Sync the prototype, the design docs, and the tests so all four stay consistent.

## Goals

- The "下一步：查询匹配报告" button is always clickable; clicking validates required fields: missing target, version, or either end of the time range (or an inverted range) does not enter step 2 — the offending inputs turn red with a red hint below them, and each error clears as soon as the field is fixed.
- Zero hits (`409 NO_PROBES_MATCHED`) advance to step 2: show a "no matching problem reports" empty state with adjust-the-condition guidance; both exit buttons are disabled in the empty state; all other errors keep the red step-1 display.
- Prototype, design docs, tests, and implementation stay four-way consistent, keeping the automated regression path.

## Design authority

- [plans/fullstack-design/08-frontend-implementation.md §9.1](../../../plans/fullstack-design/08-frontend-implementation.md): the state machine gates the Step1→Step2 transition on "validation passes".
- [plans/fullstack-design/08-frontend-implementation.md §9.2](../../../plans/fullstack-design/08-frontend-implementation.md): step 1 form and the "Next" behavior (currently "backend 409 on no match"; this issue changes that behavior).
- [plans/fullstack-design/08-frontend-implementation.md §9.3](../../../plans/fullstack-design/08-frontend-implementation.md): step 2 hit confirmation and the two exits.
- [plans/fullstack-design/05-api-design.md §4.9](../../../plans/fullstack-design/05-api-design.md): the `409 NO_PROBES_MATCHED` contract and the current "frontend stays on step 1" wording (updated by this issue).
- [plans/fullstack-design/09-review-guide.md](../../../plans/fullstack-design/09-review-guide.md): the wizard step1→step2 review mapping rows.
- [plans/14-15-ui-prototype/harness-evolution.html](../../../plans/14-15-ui-prototype/harness-evolution.html): the wizard prototype; its `wz-query` button has no disabled state.
- On conflicts, the linked sections and the `plans/14-15-ui-prototype/harness-evolution.html` prototype win.

## Implementation

- Remove the `:disabled` on `wizard-next`; `runQuery()` validates on click: `selectedTarget` present, `targetVersion` present, `windowFrom`/`windowTo` present, and `from <= to`.
- On validation failure: add a red border to each missing input (`aria-invalid` plus a style class) and show a red hint below it (missing-required-field copy such as 「请选择进化对象」「请选择版本」「请选择时间段」); the inverted range reuses 「起始时间不能晚于结束时间」 and is marked red too; any field edit clears that field's error; a failing validation issues no request and stays on step 1.
- When `runQuery()` catches `409 NO_PROBES_MATCHED`, treat it as an empty result: set `step = 2` and render the empty-state panel (no matching problem reports/probes plus an adjust-the-condition guide), keep the condition strip, and disable both 「启动自进化」 and 「启动问题聚类分析」 (the backend launch enforces the same rule and would 409); all other errors keep the step-1 `wizard-error` display.
- Unit tests: drop the assertions on `wizard-next`'s `disabled` attribute; add cases for "always clickable", "each missing field turns red with a hint below and no request is sent", "errors clear on input", and "`NO_PROBES_MATCHED` advances to the step-2 empty state with exits disabled"; rewrite the "conflicts when no probe matches and stays on step 1" scenario to the new behavior.
- Sync the E2E `m5-05-launch-wizard` scenarios for validation and the empty state.
- Sync the prototype (validation-error and empty-state demo branches), the design docs (05 §4.9 / 08 §9.2–9.3 / 09 review rows), and the owning Agent Note (paired locales + `record:i18n`).

## Implementation steps

1. Failing tests first: unit tests assert the button is never disabled; clicking with empty target/version/time range turns each field red with a hint below and sends no request; `409 NO_PROBES_MATCHED` advances to the step-2 empty state with exits disabled; rewrite the E2E scenario the same way and watch it fail.
2. Implement the field-level validation and the `NO_PROBES_MATCHED` → empty-state mapping in `LaunchWizard.vue`.
3. Bring the unit tests and E2E back to green.
4. Sync the prototype, the design docs (05/08/09), and the owning Agent Note (paired locales + `record:i18n`).
5. Run focused unit tests, web typecheck and lint, E2E, the flow and docs gates, and the design-token and bundle gates.

## Dependencies and boundary

- Depends on: m5-05
- Boundary: only step 1 required-field feedback, the next→step-2 empty-hit transition, the matching tests, and prototype/doc sync; the backend 409 contract and launch validation do not change.

## Verification

```sh
pnpm --filter @harness/web test -- LaunchWizard
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e --pattern m5-05
pnpm verify:flow
pnpm lint:docs
pnpm verify:web-style
pnpm verify:bundle
```

- Opening the wizard and clicking "Next" immediately marks target/version/time range red with hints below and sends no request; errors clear as each field is filled.
- Querying a condition with zero hits advances to step 2, shows the no-match empty state, disables both exit buttons, and 「修改条件」 returns to step 1.
- All gates above stay green.

## Acceptance

- `wizard-next` has no disabled state in any form state and is clickable everywhere.
- Each missing required field turns red with a red hint below; a field's error clears as soon as it is edited; the inverted range reuses the existing copy and is marked red.
- Zero hits advance to step 2: a "no matching problem reports" empty state with adjust-the-condition guidance, both exit buttons disabled; errors other than `NO_PROBES_MATCHED` still display on step 1.
- Unit tests, E2E, typecheck, lint, the flow gates, and the docs gates all stay green.

## Gates and CI

- `pnpm test:web`
- `pnpm typecheck:web` / `pnpm lint:web`
- `pnpm test:e2e --pattern m5-05`
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`
- `pnpm verify:web-style` / `pnpm verify:bundle`

## Non-goals

- The 409 contracts of `probes/query`, `runs`, and `cluster-previews` and the OpenAPI do not change.
- The model multi-select semantics (none selected = all models) and the version required-ness (backend `defaultRef` fallback unchanged) stay as-is.
- No refactor of the wizard's other steps or form logic, and no change to the configuration page or catalog invalidation semantics.
