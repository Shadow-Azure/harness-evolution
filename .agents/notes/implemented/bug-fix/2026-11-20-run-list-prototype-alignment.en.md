# Agent Note: Run-configuration labels on evolution history cards

Status: implemented

English | [中文](2026-11-20-run-list-prototype-alignment.md)

## Problem

Production "Evolution → History" cards show only the target version, time window, and models. They lack the workspace, potential-policy, and cache labels that both the V2 prototype and design document 05 §3.5 list, and their top-right meta prefixes the timestamp with the creator while the prototype shows only the time. The run configuration is already written to `evolution_runs.potential_policy` / `cache_enabled` / `workspace_id` at launch, but the list service never projects them into `EvolutionRunCard`, so this is a contract-projection gap rather than a missing style. Problem and evidence are in GitHub #414.

## Decision

- `EvolutionRunCard` gains `policy: { preset: default | custom }` and `cacheEnabled`. `policy` exposes only the display preset and never the full policy JSON with its three switches; legacy runs with a missing or unknown preset normalize to `default`, and a missing `cache_enabled` is `false`.
- The workspace name does not enter the card DTO: the list is always filtered by the current workspace, so the frontend reads the current route workspace name from the auth store and passes it down; the card DTO does not duplicate space information.
- The card's top-right meta shows only `createdAt`; the creator is no longer rendered. `createdBy` stays in the DTO (the detail inherits the same field) for later detail or audit use. Design documents 05 / 08 and the prototype agree on "the list shows only the time".
- The service `_card()` projects `policy` and `cacheEnabled` once, so `EvolutionRunDetail` inherits the snapshot and the detail and list cannot disagree on policy.

## Alternatives considered

- **Add `workspace: { id, name }` to the card DTO**: it would let a card stand alone, but the list is already workspace-scoped, so the DTO would repeat the same space on every card and the repository query would need a workspace-name join. Rejected.
- **Keep the creator prefix and add the creator to the prototype**: design document 05 §3.5 once required showing the creator, but #405 already reduced the run-detail header to "title + status + workspace badge"; keeping the creator on the list would create two conventions, and #414 explicitly recommends removing it. We remove the list display and keep the DTO field. The reverse prototype change is rejected.
- **Read policy and cache switches from the attribution / range steps in the frontend**: the detail page has those steps, but the list has no per-card step-loading path, so it would multiply requests and state complexity. The configuration is already persisted on the run row, so projecting it in the list is smaller. Rejected.
- **Expose the full `potential_policy` JSON to the frontend**: the list only needs the default / custom copy, while the full switches belong to the detail and algorithm contract; exposing them widens the frontend dependency surface. Rejected.
- **Remove the model chips to match the prototype exactly**: #414's difference table does not list models as a deviation, and removing them would lose existing information beyond this defect. Kept.

## Consequences

- The `run` / `history` cards in `GET …/evolution/runs` gain two fields, and the OpenAPI and generated types update through `pnpm contract:generate`. Old clients are unaffected; when an old server omits `policy`, the new frontend falls back to the default preset with `?.`, and a missing `cacheEnabled` renders as false, so a mixed-version tab does not throw during a release rollback.
- Legacy runs (empty `potential_policy`, default-false `cache_enabled`) show "默认潜在策略 / 不复用缓存", matching the launch default; they are never rewritten as a custom policy.
- The creator disappears from the list but stays in the DTO. If a later product requirement restores it on the list, the prototype and design documents must change together rather than only the frontend.
- The prototype gains a failed sample and failure badge so later comparisons do not treat "failed without a final line" as missing card style; the list page width still has the `.evolution-page-frame` 1080px cap, which is a separate page-frame concern this Note leaves alone.
