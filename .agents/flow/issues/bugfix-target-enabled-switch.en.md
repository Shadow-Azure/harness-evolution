# Remove the enabled switch from the evolution target form; new targets default enabled

English | [中文](bugfix-target-enabled-switch.md)

```yaml flow
kind: issue
id: bugfix-66
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - apps/web/**
  - plans/**
  - .agents/**
  - tests/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-26-target-enabled-switch.md
github:
  number: 628
  url: https://github.com/Shadow-Azure/harness-evolution/issues/628
```

## Background

The `启用` switch at the bottom of the production create/edit evolution-target form carries two meanings at once: the target's global enabled state and "enter the launch-wizard candidates". The two near-synonyms `启用` (enable) and `启动` (launch) sit on top of each other, so users cannot tell whether the switch enables the target or only adds it to the launch wizard. Code inspection confirmed that `enabled` actually gates the launch-wizard catalog, launch/probe, the background attribution queue and the target overview; describing only wizard candidacy in the form is misleading. Rewriting the copy (label `参与自进化` plus an explanation of the disabled effects) was tried first, but the feedback was that it was still too complex. Final decision: remove the option from the form, default new targets to enabled, and keep disable/enable on the existing list action.

## Goals

- Remove the `启用` form item and `ElSwitch` from `TargetFormDialog.vue`; the form goes from `主指标 key` straight to the footer actions.
- New targets submit `enabled: true`; editing a disabled target preserves the current `enabled` and does not silently re-enable it.
- Keep the `已启用/已停用` status and `启用/停用` action in the target list as the only state-switching entry point.
- Do not change the backend, contracts, database fields or launch/attribution/overview behavior.

## Design authority

- [08 §9.5 Evolution target configuration page](../../../plans/fullstack-design/08-frontend-implementation.md#95-进化对象配置页evolutiontargets): form fields, required validation and save behavior.
- [V2 prototype `plans/ui-prototype-v2/harness-evolution.html`](../../../plans/ui-prototype-v2/harness-evolution.html): form shape and screenshot comparison after removing the switch.
- [GitHub issue #628](https://github.com/Shadow-Azure/harness-evolution/issues/628): ambiguity report, user decision and before/after prototype screenshots.

## Implementation

- `apps/web/src/pages/evolution/targets/components/TargetFormDialog.vue`: remove the `ElFormItem label="启用"` block and `.switch-row` style; keep the `form.enabled` initialization (`props.target?.enabled ?? true`) and submitted field.
- `apps/web/src/pages/evolution/targets/components/TargetFormDialog.test.ts`: drop the `.el-switch` assertions; cover create submitting `enabled: true`, editing a disabled target keeping `enabled: false`, and the form no longer exposing `.el-switch` or the `进入启动向导候选` copy.
- `plans/ui-prototype-v2/harness-evolution.html`: remove the enable switch from the prototype form.
- `plans/fullstack-design/08-frontend-implementation.md` §9.5: update the form tree and add the new-target default, edit preservation and list-action boundary.
- `tests/e2e/m5-target-config.test.mjs`: after disabling a target, edit it and assert the form has no switch and the target stays disabled; keep the list-toggle coverage.
- Agent Note: record why the switch was removed, the rejected copy rewrite, and the decision to keep state switching in the list.

## Implementation steps

1. Update the component tests first to cover default-enabled creation and a disabled target staying disabled on edit.
2. Remove the form switch and `.switch-row` style while keeping the `form.enabled` initialization and submission.
3. Update the design doc and prototype; run focused unit tests, typecheck, lint and flow/docs gates.
4. Real-browser smoke: a new target is `已启用`; editing a disabled target keeps it `已停用`; the list action toggles state.

## Dependencies and boundary

- Dependencies: none.
- Non-goals: do not change the backend meaning of `enabled`, API contracts, database fields or launch/attribution/overview behavior; do not remove the list's `停用/启用` action; do not add a second switch.

## Verification

```sh
pnpm test:web -- src/pages/evolution/targets
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "m5 target configuration"
pnpm verify:flow
pnpm lint:docs
```

- Component tests cover create `enabled: true`, edit of a disabled target `enabled: false`, and the form having no `.el-switch` and no `进入启动向导候选` copy.
- The target-config E2E edits a disabled target and asserts the form has no switch and the stored target remains disabled.
- Browser smoke covers create, edit-disabled and list-toggle paths, with screenshots compared at the same viewport as the V2 prototype.
- The commands above are all green.

## Acceptance

- The create/edit form no longer shows `启用`, `进入启动向导候选` or any replacement switch.
- A new target is created as `已启用`; a disabled target stays `已停用` after editing.
- The list's `停用/启用` action still toggles state; the status chip and filters are unchanged.
- Before/after screenshots are captured from the same V2 prototype, same 1500×837 CSS @2x viewport; the PR shows both.

## Gates and CI

- `pnpm test:web`, `pnpm typecheck:web`, `pnpm lint:web`.
- `pnpm verify:flow`, `pnpm lint:docs`, `pnpm test:gates`.
- GitHub CI must pass; the maintainer merges.

## Non-goals

- Do not change the backend meaning of `enabled`, API contracts, database fields or launch/attribution/overview behavior.
- Do not remove the `停用/启用` action from the configuration list, and do not change its status copy.
- Do not add a second "wizard only" switch, and do not add replacement explanatory copy to the form.
- Do not reorder the other form fields.
