# Align the evolution run detail with the V2 prototype

English | [中文](m21-run-detail-prototype-alignment.md)

```yaml flow
kind: issue
id: m21-01
milestone: m21
depends:
  - m10-06
priority: P2
status: done
scope:
  - apps/web/**
  - tests/e2e/**
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr:
  - ../../notes/implemented/feature/2026-11-19-run-detail-prototype-alignment.md
github:
  number: 405
  url: https://github.com/Shadow-Azure/harness-evolution/issues/405
```

## Background

The production "Evolution → Run detail" page drifts from the V2 prototype in hierarchy, field set, and counting: a standalone "Workspace" card pushes "Flow progress" behind a third card; "Goal and input" carries a "Models (multi-select)" field that neither the prototype nor the design document has, and lacks "Workspace", "Attributed / non-target", and policy/cache source badges; the header adds creator · time; the distribution title counts concluded attributions. The prototype itself lacks the "Execution log" tab and "preparing" state required by design document 08 §10.2 / §10.4, so the same page cannot be accepted against the prototype. See [GitHub #403](https://github.com/Shadow-Azure/harness-evolution/issues/403) for the full comparison and screenshot evidence.

## Goals

- Restore the run detail to the single-column hierarchy in the prototype and design document: header (title + status + workspace badge) → goal and input → flow progress → current step output.
- Use the prototype field set in "Goal and input": target / version / window / workspace, associated Sessions, bad cases in window, potential bad cases, attributed / non-target, plus policy and cache source badges. Workspace, push, and eval information move into a collapsible area of the same card, and the branch name stays copyable.
- Unify the distribution title and legend to "attribution conclusion distribution of potential bad cases", including non-target, reused cache, and new-this-run splits; the underlying counting stays unchanged.
- Keep the "Seven steps / Execution log" tabs and the "preparing" state, and close the prototype gap in the same PR by updating the V2 prototype and design document 08.
- Do not change the API contract, attribution / clustering / eval algorithms, SSE, seven-step keys, or pagination.

## Design authority

- [08 §10.1 structure / §10.2 interaction / §10.4 execution log](../../../plans/fullstack-design/08-frontend-implementation.md): detail hierarchy, workspace and policy/cache chips in infoPanel, execution-log tab, preparing state.
- [V2 prototype run detail](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html): `evInfoPanel()` field order, distribution title and legend, policy/cache badges.
- [05 run detail DTO](../../../plans/fullstack-design/05-api-design.md): existing fields of `EvolutionRunDetail`, `EvolutionRunStats`, `EvolutionStepRange`, and `EvolutionStepAttribution`.
- [Agent Note](../../notes/implemented/feature/2026-11-19-run-detail-prototype-alignment.en.md): field choices, data sources, and prototype completion decisions.

## Implementation

- `apps/web/src/pages/evolution/RunDetail.vue`: header becomes title + status + workspace badge (workspace name from the auth store with — as fallback), dropping creator · time; remove the standalone `workspace-panel` and fold workspace fields plus local paths into infoPanel; remove "Models (multi-select)" and the standalone "Reused cache attributions" field, add "Workspace", "Attributed / non-target", policy/cache badges, and "new this run".
- Data sources: policy/cache switches come from the range step's `condition.policy` / `condition.cacheEnabled`; non-target, reused cache, and new-this-run are counted per row from the attribution step's `rows` (`category` null means non-target, `source` cached / fresh; new-this-run counts only fresh attributed rows). Until attribution finishes those show `—` and a not-attributed remainder completes the distribution bar. Both step queries are enabled by `run.steps[].clickable` and the steps tab, and share query keys with the selected step.
- Distribution: the type bar and legend use `stats.potential` as the denominator, keep error / prompt / model segments, and add a non-target segment; the legend ends with "＝ attributed N · reused cache N · new this run N".
- `plans/ui-prototype-v2/harness-evolution.html`: add the "Seven steps / Execution log" tabs and log panel to the detail page, a workspace badge to the header, a workspace collapsible area to infoPanel, and a preparing example run with its state styles.
- `plans/fullstack-design/08-frontend-implementation.md`: add the distribution wording, workspace collapse, and workspace badge to §10.1; state the tab shape in §10.4.

## Implementation steps

1. Re-layout the header, infoPanel, workspace collapsible area, and progress order in `RunDetail.vue`, wiring the range / attribution step data.
2. Update `RunDetail.test.ts` to cover the field set, workspace location, policy/cache badges, distribution copy, retained tabs, and preparing state; adjust request assertions affected by the extra step queries.
3. Update `tests/e2e/m10-06-run-detail-v2.test.mjs` to assert the header workspace badge, goal-and-input fields, progress order, absence of a standalone workspace card, and the execution-log tab.
4. Complete the V2 prototype tabs, log panel, workspace badge, workspace collapsible area, and preparing example; update design document 08.
5. Run focused unit tests, typecheck, E2E, and doc / flow gates; put before / after screenshots in the PR description.

## Dependencies and boundary

- Dependency: m10-06 (seven-step run detail and execution log already shipped).
- Non-goals: do not change `apps/api/**`, `packages/contracts/**`, attribution / clustering / eval algorithms, SSE, seven-step keys, or pagination; do not change step content components; do not commit production screenshots to fixtures; do not rework the launch wizard or evolution list.

## Verification

```sh
pnpm --filter @harness/web exec vitest run src/pages/evolution/RunDetail.test.ts src/pages/evolution/components/RunDetailConformance.test.ts
pnpm typecheck:web
pnpm test:e2e -- "m10-06"
pnpm lint:web
pnpm verify:flow
```

- Unit tests cover the header workspace badge, workspace collapse inside infoPanel, policy/cache badges, attributed / non-target, distribution title and legend, seven-step / execution-log tabs, and preparing copy.
- E2E at 1408 width asserts the workspace badge is visible, the DOM order goal-and-input → flow-progress → step output, that `workspace-panel` is absent, that workspace information sits inside infoPanel, and that the execution-log tab opens.
- `pnpm typecheck:web` and `pnpm lint:web` pass; `pnpm verify:flow` passes.

## Acceptance

- At 1408 / 1440 width the same run detail reads header (title + status + workspace badge), goal and input, flow progress, current step output; "Workspace" is no longer a standalone card.
- Goal and input shows "Workspace", "Attributed / non-target", policy/cache badges, and "new this run"; "Models (multi-select)" is gone; the branch name stays copyable.
- The distribution title is "Attribution conclusion distribution of potential bad cases (N)" and the legend includes non-target, reused cache, and new this run.
- The seven-step / execution-log tabs and the preparing state are visible in both production and the V2 prototype.
- Before / after screenshots (same scenario, same viewport) are attached to the PR description, with the baseline revision identified for the before image.

## Gates and CI

- Unit tests and coverage: `pnpm test:web`.
- Type and lint: `pnpm typecheck:web`, `pnpm lint:web`.
- E2E: `pnpm test:e2e -- "m10-06"`.
- Docs and flow: `pnpm lint:docs`, `pnpm verify:flow`; run `pnpm verify:docs` when needed.
- PR title and commits carry `(#<flow issue number>)`; deliver for human review only after CI is green.

## Non-goals

- No new or changed API fields, no new Session-total endpoint.
- No change to execution-log data source, pagination, SSE, or error display.
- No change to the evolution list, launch wizard, target config, or attribution step content.
- No production screenshots or private content committed to the repository.
