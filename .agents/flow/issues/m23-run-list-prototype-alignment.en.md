# Show workspace, potential-policy, and cache labels on evolution history cards

English | [中文](m23-run-list-prototype-alignment.md)

```yaml flow
kind: issue
id: m23-01
milestone: m23
depends:
  - m5-04
  - m10-06
priority: P2
status: done
scope:
  - apps/api/app/service/evolution/**
  - apps/api/tests/**
  - packages/contracts/**
  - apps/web/src/pages/evolution/**
  - tests/e2e/**
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-20-run-list-prototype-alignment.md
github:
  number: 418
  url: https://github.com/Shadow-Azure/harness-evolution/issues/418
```

## Background

In production, "Evolution → History" run cards show only the target version, time window, and model chips; they lack the workspace, potential-policy, and cache labels that the V2 prototype places on the second row. The card's top-right meta also prefixes the timestamp with the creator, while the prototype shows only the time. The run configuration is already stored in `evolution_runs` (`potential_policy`, `cache_enabled`, `workspace_id`); what is missing is the `EvolutionRunService._card()` projection and the `EvolutionRunCard` contract fields. Design document 05 §3.5 already lists `policy` and `cacheEnabled` in its `RunCard` example, so this is a projection gap rather than a new product requirement. Full comparison and screenshots are in [GitHub #414](https://github.com/Shadow-Azure/harness-evolution/issues/414).

## Goals

- History cards show workspace, `默认潜在策略` / `自定义潜在策略`, and `复用缓存` / `不复用缓存` after the target version and time window, in prototype order.
- The `EvolutionRunCard` contract gains `policy` with only the display preset and `cacheEnabled`; the workspace name is rendered from page context (the current route workspace), because the list is always workspace-scoped and the card DTO should not duplicate the space.
- The card's top-right meta shows only the time; the creator is no longer rendered in the list but stays in the DTO for detail and audit, with design documents 05 / 08 and the prototype agreeing.
- Legacy runs without `potential_policy` / `cache_enabled` render as default policy and no cache reuse without errors or a fabricated custom policy.
- The six statistics, status badge, completed final line, failed-without-final behavior, whole-card click, and error tooltip do not regress.

## Design authority

- [05 §3.5 Evolution runs](../../../plans/fullstack-design/05-api-design.md): `RunCard` `policy`, `cacheEnabled`, and `createdBy` fields and list semantics.
- [08 §8 Evolution list page](../../../plans/fullstack-design/08-frontend-implementation.md): history-card component tree, badge, final line, and empty state.
- [V2 prototype run list](../../../plans/ui-prototype-v2/harness-evolution.html): `evRunCard()` second-row order and the top-right time-only meta.
- [06 Evolution tables](../../../plans/fullstack-design/06-database-design.md): stored `evolution_runs.potential_policy`, `cache_enabled`, and `workspace_id`.
- [Agent Note](../../notes/implemented/bug-fix/2026-11-20-run-list-prototype-alignment.en.md): projection fields, workspace source, and the creator decision.

## Implementation

- `apps/api/app/service/evolution/runs.py`: add `EvolutionRunPolicy` (`preset: default | custom`) and project `policy` (missing or unknown preset normalizes to `default`) plus `cache_enabled` from `run`; `EvolutionRunDetail` inherits the card fields and gets the same snapshot automatically.
- `packages/contracts`: run `pnpm contract:generate` to update `openapi.json` and generated types; never hand-edit them.
- `apps/web/src/pages/evolution/components/RunCard.vue`: render workspace, policy, and cache chips after the time window; show only `createdAt` in the top-right meta; keep model chips, existing statistics, final line, and tooltip.
- `apps/web/src/pages/evolution/Index.vue` / `components/RunGroup.vue`: read the current workspace name from the auth store and pass it down; treat a missing name as an empty string rather than fabricating one.
- `apps/web/src/pages/evolution/components/RunCard.test.ts`, `Index.test.ts`, `RunGroup.test.ts`, and other card fixtures: cover default / custom, cache true / false, legacy runs without a policy, no creator rendering, and the workspace-name source.
- `apps/api/tests/m5-04-run-list/**`: service tests assert the `policy` / `cacheEnabled` projection and legacy defaults.
- `plans/ui-prototype-v2/harness-evolution.html`: keep the three labels and time-only meta; add a failed run sample with a red failure badge so later comparisons do not mistake "failed without final line" for missing style.
- `plans/fullstack-design/05-api-design.md` and `08-frontend-implementation.md`: record that `policy` / `cacheEnabled` are card fields, the workspace name comes from page context, and the creator stays in the DTO; add an Agent Note with the trade-offs.

## Implementation steps

1. Project `policy` and `cache_enabled` in the service and add default / custom / legacy API tests.
2. Run `pnpm contract:generate` and commit the contract and generated types.
3. Rework the `RunCard.vue` meta row and time display, pass the workspace name down, and update component tests.
4. Update the other `EvolutionRunCard` fixtures and Index / RunGroup tests.
5. Add the failed prototype sample and design-document updates, write the Agent Note, and run focused gates.
6. Re-capture Before / After at the same 1500×837 viewport, with Before on the main baseline, and attach them to the PR description.

## Dependencies and boundary

- Dependencies: m5-04 (run list API and grouping), m10-06 (seven-step detail and existing card consumers).
- Boundary: only the run list card, the `EvolutionRunCard` projection and contract, matching tests, the prototype sample, and design documents / Agent Note; no change to run detail, the wizard, attribution / clustering / eval algorithms, database schema, or list ordering.

## Verification

```sh
pnpm contract:check
pnpm typecheck:web
pnpm lint:web
pnpm --filter @harness/web exec vitest run src/pages/evolution/components/RunCard.test.ts src/pages/evolution/Index.test.ts src/pages/evolution/components/RunGroup.test.ts
apps/api/.venv/bin/python -m pytest apps/api/tests/m5-04-run-list -q
pnpm test:e2e -- --pattern evolution
pnpm verify:flow
```

- Expected: the contract carries `policy` and `cacheEnabled` without breakage; history cards show the three labels and the workspace name; default / custom and cache true / false copy is correct; legacy runs show default policy; the card's top-right meta shows only the time; statistics and final lines do not regress; flow gates pass.

## Acceptance

- Production history cards show workspace, potential policy, and cache labels in prototype order, with the workspace name matching the current route workspace.
- `policy.preset` and `cacheEnabled` are backend-projected; legacy rows without a policy render as default policy.
- The creator display has one explicit conclusion: the list shows only the time, `createdBy` stays in the DTO, and the prototype and design documents agree.
- Completed runs still show best / initial / Δ / accepted, and failed runs do not invent final data.
- Contract, types, unit tests, API tests, and focused E2E pass; Before / After screenshots share one viewport and are attached to the PR.

## Gates and CI

- Contract: `pnpm contract:generate` then `pnpm contract:check`.
- Static: `pnpm typecheck:web`, `pnpm lint:web`.
- Unit: `pnpm --filter @harness/web exec vitest run …`, `pnpm test:api -- -k evolution_run`.
- E2E: `pnpm test:e2e -- --pattern evolution`.
- Docs and flow: `pnpm lint:docs`, `pnpm verify:flow`, and `pnpm verify:docs` when needed.
- PR title and commits carry `(#<flow issue number>)`; CI must be green before human review.

## Non-goals

- No change to the database schema, attribution / clustering / eval algorithms, SSE, seven-step keys, or pagination.
- No change to the run detail page, launch wizard, target configuration, or attribution step content.
- No list-page layout or width rework, and no change to list ordering or the six-statistic semantics.
- No production Session content or screenshots committed into repository fixtures.
