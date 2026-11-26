# Agent Note: remove the enabled switch from the evolution target form

Status: implemented

English | [中文](2026-11-26-target-enabled-switch.md)

## Problem

The `启用` switch at the bottom of the create/edit evolution-target form carries two meanings at once: the target's global enabled state and "enter the launch-wizard candidates". The two near-synonyms `启用` (enable) and `启动` (launch) sit on top of each other, so users cannot tell whether the switch enables the target or only adds it to the launch wizard. Code inspection confirmed that `enabled` actually gates the launch-wizard catalog, launch/probe, the background attribution queue and the target overview; describing only wizard candidacy in the form is misleading. Rewriting the copy (label `参与自进化` plus an explanation of the disabled effects) was tried first, but the feedback was that it was still too complex.

## Decision

- Remove the `启用` form item and `ElSwitch` from `TargetFormDialog.vue`; the form no longer exposes `enabled`.
- New targets keep `form.enabled = props.target?.enabled ?? true` and submit `enabled: true`; editing preserves the current value and does not silently re-enable.
- Keep the `已启用/已停用` status and `启用/停用` action in the target list as the only state-switching entry point.
- Do not change the backend, contracts, database fields or launch/attribution/overview behavior; remove the switch from the prototype too.

## Alternatives considered

- **Keep the switch and rewrite it as `参与自进化 / 允许在启动向导中选择`**: it still asks users to decide a global state inside the configuration form and needs a paragraph explaining the disabled effects; the user explicitly said this was more complex. Rejected.
- **Keep the switch and add a tooltip explaining all effects**: the ambiguity moves into a hover layer, and touch/keyboard users still have to understand the `启用`/`启动` relationship. Rejected.
- **Always submit `enabled: true` from the form**: editing a disabled target would silently re-enable it, breaking the promise that the configuration is kept. Rejected.
- **Add a second "wizard only" switch**: it needs a new backend field and semantics, beyond this UI simplification. Rejected.

## Consequences

- The form is shorter and new targets are usable immediately; to disable one, use the list, where status and action are visible together.
- Editing a disabled target does not silently re-enable it, but the form no longer shows the state; users confirm it in the list.
- Tests cover create `enabled: true`, editing a disabled target keeping `false`, and the form having no switch or legacy copy; existing list-action tests stay unchanged.
- Real-browser smoke covers create, edit-disabled and list toggle; the PR carries Before/After screenshots and does not commit them to the repository.
