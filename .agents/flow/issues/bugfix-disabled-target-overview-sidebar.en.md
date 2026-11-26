# Show disabled evolution targets greyed out in the overview sidebar without counting them

English | [中文](bugfix-disabled-target-overview-sidebar.md)

```yaml flow
kind: issue
id: bugfix-65
milestone: bugfix
depends:
  - m11-03
  - m11-04
priority: P2
status: ready
scope:
  - apps/api/app/api/overview.py
  - apps/api/app/service/overview/**
  - apps/api/app/db/crud/evolution_targets.py
  - apps/api/tests/**
  - apps/web/src/pages/overview/**
  - apps/web/src/api/**
  - apps/web/src/composables/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 626
  url: https://github.com/Shadow-Azure/harness-evolution/issues/626
```

## Background

Production «Overview → Evolution targets» reads only `enabled=true` targets: `TargetOverviewService._analyses` hard-codes `enabled_only=True`, and `GET /api/workspaces/{wid}/overview/targets` covers only enabled targets in `summary` and `items`. After a space admin disables a target, it disappears from the whole overview — the top stats drop, the right «Evolution targets» list no longer shows it, and there is no entry showing that the configuration still exists but is disabled. The user confirmed disabled targets should remain in the right sidebar without entering other statistics.

This issue only addresses visibility: disabled targets remain at the end of the sidebar, greyed out and marked «Disabled», and can be enabled, edited or removed; after re-enabling, they return to normal ordering and stats. Disabling keeps its existing meaning for the launch wizard, binding batches, attribution and runs.

## Prototype comparison

Same V2 prototype, same page state (`?u=admin&ws=ws-harness&page=overview&tab=targets`), 1500×1200 CSS viewport, 2× DPR, light theme; the data is the `ws-harness` synthetic fixture (3 enabled targets + 1 disabled `release-notes`). Click an image to open the full size.

| Before (current main prototype) | After (prototype in this issue) |
| --- | --- |
| [![Before: the sidebar shows only 3 enabled targets](https://github.com/Shadow-Azure/harness-evolution/releases/download/disabled-target-overview-evidence-20261126/baseline-overview-targets.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/disabled-target-overview-evidence-20261126/baseline-overview-targets.png) | [![After: the disabled release-notes appears greyed out at the end of the sidebar with an Enable button](https://github.com/Shadow-Azure/harness-evolution/releases/download/disabled-target-overview-evidence-20261126/disabled-target-overview-targets-enable.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/disabled-target-overview-evidence-20261126/disabled-target-overview-targets-enable.png) |

The left image shows only 3 enabled targets and a pager reading «3 total»; the right image adds a «Disabled targets» group at the end, where `release-notes @v1.2.3` is greyed out with a «Disabled» badge and an «Enable» button, while the top stat strip still shows 3 targets, 18 associated Sessions and 31 potential bad cases. The charts, distributions and per-target analysis card are identical in both images.

## Goals

- After the enabled targets, show every disabled target in the sidebar, greyed out and marked «Disabled»; show only object/version, attribution Skill and enable/edit/remove entries.
- Keep disabled targets out of the top stat strip, trend chart, both distributions, the per-target analysis selector, filter dropdowns and the potential bad case list.
- Return disabled target metadata as a separate API field; keep the existing `items`, `total`, `summary` and every enabled-target calculation unchanged.
- After re-enabling, return the target to normal sidebar ordering and statistics.
- Provide before/after screenshots from the same prototype, viewport and page state.

## Design authority

- [08 §6 Workspace overview](../../../plans/fullstack-design/08-frontend-implementation.md#6-工作空间总览页pagesoverviewindexvuev2): the `TargetSideList.vue` position, 5-item paging and target overview layout.
- [05 §4.18 Overview and workspace Session lists](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2): the `GET /overview/targets` `summary/items/total` contract.
- [06 §5.1 Evolution target configuration](../../../plans/fullstack-design/06-database-design.md#51-evolution_targets--可自进化的对象配置): the existing `enabled=false` semantics (not a wizard candidate, no binding batch).
- [V2 design §5.3 Dual view](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/design-v2.md#53-双视角bad-case--进化对象): the right target list and the disabled-target group.
- [V2 prototype sidebar](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html): the enabled list and disabled group in `v2RenderTargetsOverview`.

## Implementation

- Contracts: add `TargetOverviewDisabledItem` (`targetId`, `objectType`, `objectName`, `attributionSkillName`, `defaultRef`) to `packages/contracts`, and add a `disabled` list to `TargetOverviewListResponse`; keep `items` and `summary` on the enabled-target contract. Run `pnpm contract:generate` to refresh the generated OpenAPI types.
- API: keep `TargetOverviewService.list_targets` enabled-target analysis and summary as-is; additionally read the same space with `enabled_only=False`, filter to disabled targets, sort by object name and write them to `disabled`. Keep `trend`, `cases` and `detail` on enabled targets only, with no new endpoint.
- Web data: expose `disabled` from `useOverviewTargets`; pass it from `TargetsOverview` to `TargetSideList` without merging it into `targetItems`, so filters, charts, distributions, the detail selector and the potential bad case list never see disabled targets.
- Web rendering: after the paged enabled targets, `TargetSideList` appends a «Disabled targets» group; each item shows object/version, attribution Skill and a «Disabled» badge, is greyed out, and keeps enable/edit/remove; editing opens the existing target form.
- Enable action: each disabled item offers «Enable»; clicking calls the existing `useEvolutionTargets().updateTarget` with `enabled=true`, invalidates the overview on success and moves the target back to the enabled list; a failure shows the server error and does not optimistically toggle locally.
- Tests: API coverage that `disabled` is returned while `summary`/`total` exclude disabled targets; component coverage for group order, badge, non-selectability, enable and edit/remove events; E2E coverage that the sidebar shows the disabled target and that enabling it returns the target to the enabled list with statistics restored.
- Docs: update `08 §6` and `05 §4.18` during implementation; the prototype side already updates `design-v2.md §5.3`.

## Implementation steps

1. Add the contract field and API tests first, confirming the enabled `summary`, `items` and `total` stay unchanged.
2. Implement the disabled-target read and stable sort in `list_targets`, then run the API and contract gates.
3. Wire the Web data flow and the `TargetSideList` group, then add component tests.
4. Wire enable/edit/remove and the re-enable path, then add E2E and same-viewport screenshots.
5. Update the frontend design docs and run the repository gates.

## Dependencies and boundary

- Dependencies: m11-03 (target overview API) and m11-04 (target overview UI).
- Boundary: add only the disabled-target display and read-only metadata to the target overview; do not change the target configuration page, launch wizard, binding batches, attribution, runs, permissions or any enabled-target statistic.
- Disabled targets may be enabled/edited/removed but expose no historical stats or detail drill-down; the sidebar pager may include disabled targets, while top stats, charts and lists never do.

## Verification

```sh
pnpm test:api -- tests/m11-03-target-overview
pnpm --filter @harness/web exec vitest run src/pages/overview
pnpm typecheck
pnpm contract:check
pnpm test:e2e -- --pattern target-overview
pnpm verify:flow
```

- API: with the same fixture, `disabled` contains the disabled target; `summary.targets` and `items` contain enabled targets only; `trend`, `cases` and `detail` never include the disabled target.
- Web: the sidebar ends with a «Disabled targets» group and a «Disabled» badge; filter dropdowns, the per-target selector, charts and the potential bad case list exclude the disabled target.
- Visual: at 1500×1200 CSS viewport, 2× DPR and light theme, the before/after screenshots of the same page state are comparable and the stat strip values are unchanged.

## Acceptance

- A disabled target is visible in the overview sidebar, greyed out, marked «Disabled», and can be enabled, edited or removed.
- Adding the disabled target changes none of the six top stats, the trend chart, both distributions, the per-target analysis card, filter options or the potential bad case list.
- Enabled targets still sort by evolvable count descending and page by 5; after re-enabling, a disabled target returns to normal ordering and statistics.
- The API contract carries the disabled-target metadata without breaking existing client fields.

## Gates and CI

- Hit by: API unit tests, Web unit tests, E2E, `pnpm typecheck`, `pnpm lint:web`, `pnpm contract:check`, `pnpm verify:flow`, `pnpm lint:docs` and the full CI gates.

## Non-goals

- Do not change what `enabled=false` means for the launch wizard, binding batches, attribution or runs.
- Do not expose historical statistics, detail drill-down or a new filter dimension for disabled targets.
- Do not add an API endpoint, page, permission or batch disable/enable capability.
- Do not change the enable toggle or form fields on the target configuration page.
