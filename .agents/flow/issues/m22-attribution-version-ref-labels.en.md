# Attribution list shows digest instead of tag / commit and needs truncation and copy

English | [中文](m22-attribution-version-ref-labels.md)

```yaml flow
kind: issue
id: m22-01
milestone: m22
depends:
  - m17-01
priority: P2
status: in-progress
scope:
  - plans/**
  - apps/api/**
  - apps/web/src/pages/errors/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - scripts/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-20-attribution-version-labels.md
github:
  number: 416
  url: https://github.com/Shadow-Azure/harness-evolution/issues/416
```

## Background

On 2026-11-20 the production Session error view's left-hand "Attribution · by evolution object" list showed the version as `digest:580c97cf…` (71 characters). The version could not shrink or ellipsize; it squeezed out the object name `systematic-debugging`, overlapped the "cached / attributed" badges, and spilled out of the card. The overview version row already shows ref + short commit via m17 (#389), but the attribution list still reads only `probe_reports.object_version` (digest). The contract has no ref / commit, and there is no truncation, full-value affordance, or copy entry. The V2 prototype's default samples use short tags and hide the problem; injecting the same digest into the prototype reproduces the overlap, so the prototype structure also lacks long-version handling.

## Prototype evidence

**Before / after (same data, same 1500×837 @2x viewport)**

[![Attribution version label Before / After](https://github.com/Shadow-Azure/harness-evolution/releases/download/attribution-version-labels-evidence-20261120/attribution-version-before-after.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/attribution-version-labels-evidence-20261120/attribution-version-before-after.png)

**After: hovering a truncated value reveals the full digest above**

![Full digest on hover](https://github.com/Shadow-Azure/harness-evolution/releases/download/attribution-version-labels-evidence-20261120/attribution-version-tooltip.png)

**After: full prototype page**

![Full prototype page](https://github.com/Shadow-Azure/harness-evolution/releases/download/attribution-version-labels-evidence-20261120/attribution-version-full.png)


## Goals

- When a ref exists, the attribution item shows the ref + short commit (matching the overview version row); with only a commit it shows the short commit; with only a digest it keeps a digest fallback.
- Long versions truncate; hover or focus reveals the full value above the version; a small copy button beside it copies the full version identifier (commit first, digest fallback).
- A long version never squeezes out the object name, overlaps cache / conclusion badges, or spills out of the card.
- Update the V2 prototype first with same-viewport Before / After; the production API contract and frontend then follow the prototype.
- Do not change attribution matching, cache keys, statistics, or conclusion semantics.

## Design authority

- [08 §7.1 Error detail layout and data](../../../plans/fullstack-design/08-frontend-implementation.md): the attribution item carries the conclusion badge, time, cache marker, and locate action; this issue adds the version-label display rule.
- [15 §9.2 Object revision and model identity](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md#92-对象-revision-与模型身份): `targetVersion` is the readable ref and `targetRevision=digest:<sha256>` drives matching and caching; the display layer should retain the ref.
- [m17 #389 object-card version display](https://github.com/Shadow-Azure/harness-evolution/issues/389): the overview version row already renders ref + short commit; this issue extends the same rule to the attribution list.
- [V2 prototype](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html): `ErrorApp`'s attribution list and the version row in `v2TargetDetailCard()`.

## Implementation

**V2 prototype (first PR of this issue)**

- `ErrorApp` attribution items render `ref` + short commit; without a ref they show the short commit or a truncated digest. The version area can shrink and ellipsize, and the copy button copies the full identifier.
- Hover or focus shows a full-version layer; the layer attaches to a page-level node so `.err-case` / `.err-list` overflow cannot clip it.
- Extend prototype attribution data: known versions carry ref / commit and digest-only historic items keep the fallback; injecting the same digest no longer overlaps.

**Production API and frontend (later PR)**

- Add nullable `objectRef` / `objectCommit` (or an equivalent version option) to `AttributionItem`, populated from the run's `target_version` / `target_revision` / `base_commit`; leave them empty and keep the digest when only digest evidence exists.
- Regenerate the contract with `pnpm contract:generate`; the attribution read path only reads existing data and performs no writes or git-ref reverse lookups.
- `AttributionItem.vue` follows the prototype for ref + short commit, truncation, full-value layer, and copy button; CSS keeps a long value clear of the badges.
- Unit tests cover ref / commit / digest inputs, copy, and tooltip; E2E covers the long-digest no-overlap case.

## Implementation steps

1. Update the V2 prototype and capture same-viewport Before / After with the same injected data; attach the screenshots to this issue.
2. Extend the `AttributionItem` contract and API read, then regenerate contracts.
3. Update `AttributionItem.vue` and styles, with component tests.
4. Add E2E, the Agent Note, and design document 08 §7.1.
5. Deliver the production implementation after all gates pass.

## Dependencies and boundary

- Depends on m17-01 (done): reuse its ref / short-commit display rule and run evidence.
- The first PR of this issue only changes the V2 prototype, flow files, and the Agent Note; production implementation follows under the same issue.
- No new data source, no git-ref reverse lookup for historic digests, no change to attribution matching / caching / pagination / statistics.
- Do not commit production Session content or user screenshots to the repository.

## Verification

```sh
pnpm verify:flow
pnpm lint:docs
```

- Render the attribution item at 1500×837 @2x: ref + short commit looks right; after injecting a 71-character digest the version truncates, the object name stays visible, and badges do not overlap; hover reveals the full digest; the copy button copies the full digest.
- Production phase adds: `pnpm contract:check`, `pnpm typecheck:web`, `pnpm lint:web`, `pnpm test:web`, `pnpm test:e2e -- --pattern <attribution-list case>`.

## Acceptance

- A ref shows ref + short commit; commit-only shows the short commit; digest-only shows a truncated digest.
- A long version no longer squeezes out the object name or overlaps cache / conclusion badges, and the card does not overflow.
- Hovering a truncated value reveals the full value above it; the copy button copies the full version identifier and reports success.
- The prototype Before / After matches the issue screenshots; the production implementation is comparable in the same region.
- Attribution matching, cache keys, pagination, statistics, and conclusion semantics stay unchanged.

## Gates and CI

- `pnpm verify:flow`, `pnpm lint:docs`; the production phase adds `pnpm contract:check`, `pnpm typecheck:web`, `pnpm lint:web`, `pnpm test:web`, `pnpm test:e2e`.
- PR and commit titles reference this issue's GitHub number.

## Non-goals

- Do not change `digest:<sha256>` as the canonical matching and cache key.
- Do not reverse-lookup git refs / tags for historic digest-only attributions.
- Do not reorder other attribution fields or change pagination, filters, selection, or deep links.
- Do not change the already-completed object-overview version display.
