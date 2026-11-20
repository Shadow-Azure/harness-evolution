# Target-card version rows show digests instead of refs and commit ids

English | [中文](m17-target-version-ref-labels.md)

```yaml flow
kind: issue
id: m17-01
milestone: m17
depends: []
priority: P2
status: done
scope:
  - apps/api/app/service/overview/**
  - apps/api/app/db/crud/**
  - apps/api/app/service/evolution/**
  - apps/api/tests/**
  - apps/web/src/pages/overview/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - .agents/notes/**
  - .agents/flow/**
  - docs/**
  - scripts/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-19-target-version-ref-labels.md
github:
  number: 389
  url: https://github.com/Shadow-Azure/harness-evolution/issues/389
```

## Background

Production feedback on 2026-11-19: in Overview → evolution-target overview → Single evolution-target analysis → Potential bad-case distribution, the version rows for `systematic-debugging · skill` show `digest:580c97cf8ca7901…` and `digest:8e54e1438967ef9…`. Those versions came from git refs, but the display layer kept only the content digest, while the V2 prototype shows `ref + short commit` in the same region. The production capture, the zoomed red box, and the prototype comparison are in [issue #389](https://github.com/Shadow-Azure/harness-evolution/issues/389).

The root cause is version discovery in the target overview: `agent_events.object_version` and `object_revision` are treated as independent versions, so `main` and `digest:8e54…` from one trigger record split into two rows. `TargetDetailVersion` exposes only `version`, leaving the frontend no ref or commit. `evolution_runs` stores `target_version` (ref), `target_revision` (digest), and `base_commit`, but the target-card read path never uses that association.

## Goals

- When a version came from a tag, branch, or commit id, the version rows and multi-select show that ref, plus the short commit when a run recorded one.
- When one trigger record carries both a ref and a digest, merge them into one row, prefer the ref, and do not double count.
- Digest-only historical versions stay visible; the page neither goes blank nor loses version counts.
- Version filtering, coverage counts, potential/distinct counts, Session association, attribution, and cache-key semantics stay unchanged.

## Design authority

- [15 §9.2 Object revision and model identity](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md#92-对象-revision-与模型身份): `targetVersion` is the user-selected ref, `targetRevision=digest:<sha256>` serves association, matching, and cache keys, and the selected ref remains the version/display and code baseline.
- [05 §4.18 Overview and workspace Session lists](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2): the host chapter for the target overview and detail contracts.
- [V2 prototype](../../../plans/ui-prototype-v2/harness-evolution.html): `v2TargetVersions()` and `v2TargetDetailCard()` model versions as `{ref, commit, date}` and render `ref + commit` in rows and the multi-select.
- Agent Note: [2026-11-19-target-version-ref-labels](../../notes/implemented/bug-fix/2026-11-19-target-version-ref-labels.en.md).

## Implementation

**Version aggregation**

- Version discovery changes from "one version per `object_version` / `object_revision`" to aggregation by trigger record: a ref and a digest from the same record are two identities of one version; the digest becomes the canonical match/filter key and the ref becomes the primary label.
- When one digest maps to several refs, the display ref follows the latest run's `target_version`, otherwise `defaultRef`, otherwise natural order; identical digests across records merge.
- Digest-only records are not backfilled from git and keep the digest; legacy ref-only records keep the ref version.

**Run evidence**

- The overview repository adds a bounded read-only query for `evolution_runs` by workspace and object; it associates `base_commit` through `target_revision` (preferred) or `target_version` and keeps the short commit. When only a run links the default ref and a digest, that run's ref↔digest evidence also merges them. It never writes.

**Contracts and frontend**
- `TargetOverviewItem` / `TargetDetailTarget` gain `versionOptions: [{version, ref, commit}]`; `TargetDetailVersion` gains nullable `ref` / `commit`; `versions` remains the canonical filter key.
- The version multi-select and version rows in `TargetDetailCard` render ref plus a faint short commit per the prototype; the digest fallback keeps showing; checkbox values, URL state, and statistics keep using the canonical key.
- The primary version label in `TargetSideList` uses the ref as well.

**Tests and docs**

- API unit tests cover ref+digest merging, run commits, the digest fallback, multi-ref priority, and filter compatibility; component tests cover multi-select and row rendering; a real-browser smoke covers the target card and filtering.
- Update the Agent Note and the design document's target-card version-display convention; Before / After captures go into the PR description and are not committed.

## Implementation steps

1. Add the run-version evidence query and record type in `db/crud/overview_targets.py`.
2. Aggregate ref/digest identities and attach run commits in `service/overview/targets.py`, extending `TargetAnalysis`.
3. Update `target_schemas.py` and the contracts, then run `pnpm contract:generate`.
4. Update `TargetDetailCard.vue`, `TargetSideList.vue`, and their component tests.
5. Add API tests, real-browser smoke evidence, and the Agent Note, then run the focused gates.
6. Capture same-scenario Before / After screenshots and put them in the PR description.

## Dependencies and boundary

- Depends on: nothing. It reads existing `agent_events` / `evolution_runs` data only; no extra resources or credentials.
- Non-goals: no change to `PotentialMatcher`, attribution cache keys, Session association, or probe semantics; no git-ref backfill for digest-only history; no change to other target-card regions or the version-filter interaction.

## Verification

```sh
pnpm test:api -- tests/m11-03-target-overview
pnpm test:web -- --run apps/web/src/pages/overview
pnpm test:e2e -- m11-04
pnpm contract:check
pnpm typecheck:api
pnpm typecheck:web
```

- With a ref+digest record, `versions` contains one canonical key, `versionOptions` gives the ref, and `byVersion` has one row without double counting.
- With a run record, `TargetDetailVersion.commit` is the short commit; digest-only history keeps the digest and loses no counts.
- The version multi-select and rows show ref + commit; filtered statistics match the previous behavior.

## Acceptance

- With equivalent data (`main` / `v6.4.1` and their digests), the target-card version rows and multi-select show the refs instead of long digests, plus short commits when runs exist.
- Digest-only historical versions remain visible; the page is not blank and loses no version counts.
- Version selection, filtered distribution, coverage count, distinct counts, Session association, attribution, and cache keys keep their semantics.
- Before / After captures are comparable with the same V2 prototype region and appear in the PR description.

## Gates and CI

- `pnpm contract:check`, `pnpm typecheck:api`, `pnpm typecheck:web`, `pnpm lint:api`, `pnpm lint:web`, `pnpm test:api`, `pnpm test:web`, `pnpm test:e2e`, `pnpm lint:docs`, `pnpm verify:flow`.
- New tests cover ref/digest merging, run commits, the digest fallback, and frontend rendering.
- The PR title and commit subjects reference this issue's GitHub number.

## Non-goals

- No refactor of version matching or the attribution pipeline; `digest:<sha256>` remains the only identity.
- No git-ref lookup for historical digests and no new version data source or migration.
- No change to multi-select interaction, the default newest-N window, or `versionLimit` semantics.
