# Run detail iteration source bad case titles show the short title

English | [中文](bugfix-iteration-source-short-title.md)

```yaml flow
kind: issue
id: bugfix-45
milestone: bugfix
depends:
  - m21-01
priority: P2
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - tests/e2e/**
  - plans/**
  - .agents/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 570
  url: https://github.com/Shadow-Azure/harness-evolution/issues/570
```

## Background

In production "Self-evolution → Run detail → Step 6 Iteration" the source bad case table renders the attribution report summary as the title: this run has 20 rows of 422–1541 characters (795 on average), each row becomes several paragraphs and pushes object_name, type, trigger point, and reported time to the far right, so the cases covered by that iteration cannot be checked row by row; step 5 "Clustering and severity" reuses the same projection and has the same problem. The production `bad-cases/{id}` endpoint returns a 47-character `title` and the long text in `reason`, so the two text tiers already exist in the data and the projection reads the wrong field.

The root cause is `_cluster_cases()` in `apps/api/app/service/evolution/stages.py`: the V2 branch reads `attribution_by_case[bad_case_id].probe_description` and the legacy branch reads `row.probe_description`, both writing the attribution summary into `StepClusterCase.title`; `_RunFacts` only loads candidates, attributions, and probes, never `bad_cases.title`, so the projection has nothing else to use. `git log -S "title=row.probe_description"` points at #299: the seven-step projection has behaved this way since it was introduced and this is not a later regression.

## Goals

- Step 6 "Source bad case" title column shows the source bad case short title (`bad_cases.title`), matching the V2 prototype.
- Step 5 "Clustering and severity" source table restores the short title as well.
- Step 4 "Object attribution" keeps showing the long attribution text in its description column.
- No new contract field, no frontend component change, and no historical run re-preparation.

## Design authority

- [05 §3.4 Problem (bad_case), attribution state and probe](../../../plans/fullstack-design/05-api-design.md#34-问题bad_case归因状态与-probe): `title` is the required short title and `reason` the description body; the DB mapping is `title ↔ bad_cases.title`.
- [05 §3.6 Seven-step outputs (seven independent endpoints)](../../../plans/fullstack-design/05-api-design.md#36-七步产出七个独立端点): `clusters[].cases[]` carries `badCaseId/title/objectName/badCaseType/triggerAt/createdAt`, and the cluster title is the `title` of the most frequent bad case in the cluster.
- [08 §10.3 Step6 iteration card](../../../plans/fullstack-design/08-frontend-implementation.md#103-step6-迭代卡): the first block of the expanded content is the cluster's source bad case list.
- [V2 prototype](../../../plans/ui-prototype-v2/harness-evolution.html) `evCaseTable()`: the title column renders `x.title` and `detail` never enters that column.
- [issue #165](https://github.com/Shadow-Azure/harness-evolution/issues/165): the established two-tier short title and description design.
- [issue #444](https://github.com/Shadow-Azure/harness-evolution/issues/444): precedent for the same "short field exists in the data path but the projection dropped it" fix.

## Implementation

- `apps/api/app/db/crud/bad_cases.py`: add a read-only batch method that loads `title` by `bad_case_id` with one `IN` query; no new table or migration.
- `apps/api/app/service/evolution/stages.py`: add a case-title map to `_RunFacts`; `_facts()` loads the titles of the cases in this run once, covering both the candidate and the legacy probe path.
- `apps/api/app/service/evolution/stages.py`: `_cluster_cases()` uses the short title in both the V2 and legacy branches; an abnormally missing title falls back to `bad_case_id` instead of `probe_description`; `probe_description` stays only where step 4's `StepAttributionRow.description` already uses it.
- `apps/api/app/main.py`: inject the bad case read repository into `EvolutionStageService`.
- Tests: build a V2 and a legacy run with a short `bad_cases.title` and an over-long `probe_description`; assert `steps/clusters` and `steps/iteration` return the short title in `cases[].title` while `steps/attribution` keeps the long text in `rows[].description`.
- Add an Agent Note recording the title/description text boundary in the seven-step projection.

## Implementation steps

1. Add the `bad_cases.title` batch read and thread the title map through `_RunFacts`.
2. Update both branches of `_cluster_cases()` and add the missing-value guard.
3. Add regression tests for the V2 and legacy projection paths.
4. Run the service locally with equivalent data and check steps 5/6 source tables against step 4 descriptions.
5. Add the Agent Note, run the gates, and open the PR.

## Dependencies and boundary

- Dependency: m21-01
- Boundary: only the `title` data source of the step 5/6 source bad case table and its tests; the attribution summary generation, clustering algorithm, contract fields, and historical snapshots stay as they are.

## Verification

```sh
apps/api/.venv/bin/python -m pytest apps/api/tests/evolution -q
pnpm contract:check
pnpm typecheck:api
pnpm verify:flow
```

- `cases[].title` in `steps/clusters` and `steps/iteration` equals `bad_cases.title` (47 characters in the production sample) instead of a 422–1541 character attribution summary.
- `rows[].description` in `steps/attribution` still equals the attribution summary, proving the two text tiers are not mixed.
- `pnpm contract:check` reports no diff, proving the contract is unchanged.

## Acceptance

- The step 6 iteration card's "Source bad case" title column shows 47-character short titles (for example `[SWE-bench] astropy__astropy-13236 · unresolved`) instead of attribution analysis text.
- The step 5 "Clustering and severity" source table shows the short title as well.
- The step 4 "Object attribution" description column still shows the full attribution summary.
- The contract is unchanged and historical runs render without re-preparation.
- New tests cover both the V2 and legacy projection paths.

## Gates and CI

- `pnpm test:api`, `pnpm typecheck:api`, `pnpm contract:check`, `pnpm verify:flow`, `pnpm verify:docs`.
- The PR title and commit subjects reference this issue's GitHub number.

## Non-goals

- No new `StepClusterCase` field and no OpenAPI or generated-type change.
- No CSS truncation, `line-clamp`, or "first N characters" masking of the long text.
- No change to `probe_description` generation, caching, or the step 4 display.
- No change to the cluster title algorithm, cluster description, severity, or clustering process.
- No cleanup of existing `bad_cases.title` values that are themselves too long.
