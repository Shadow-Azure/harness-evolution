# Cluster-only page renders cluster results, input summary, and cluster-stage progress

English | [中文](bugfix-cluster-preview-results.md)

```yaml flow
kind: issue
id: bugfix-10
milestone: bugfix
depends:
  - m10-04
  - m10-05
priority: P2
status: ready
scope:
  - apps/api/**
  - apps/web/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 468
  url: https://github.com/Shadow-Azure/harness-evolution/issues/468
```

## Background

[issue #466](https://github.com/Shadow-Azure/harness-evolution/issues/466) records that a production cluster-only run detail page in "evolution → cluster-only" shows only a banner, the run title, a status bar, and "target / time window"; the rest of the page is blank. The status bar also shows `completed` with `第 6/7 步 · 迭代优化 · 第 1/1 轮`. The same run's `GET /runs/{runId}/steps/clusters` already returns one cluster with rank, title, category, caseCount, confidence, and severity, but the page never requests it. The root cause is that `apps/web/src/pages/evolution/ClusterPreview.vue` has been a placeholder shell since m5-05, with no input summary, cluster list, or launch button; `_progress()` in `apps/api/app/service/evolution/runs.py` computes seven steps for every mode, so a completed `cluster_only` run at `unit=5` falls into the iteration label and 71% progress.

The V2 prototype `plans/ui-prototype-v2/harness-evolution.html` has no standalone cluster-only page; it renders clusters in run-detail step 5. The standalone "problem cluster results" page is defined by the V1 baseline prototype and [08 §11](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#11-仅聚类页pagesevolutionclusterpreviewvue). This issue keeps the existing entry point and `cluster_only` capability, completes the page per 08 §11 and the V1 baseline, and takes its visual language from the V2 step-5 cluster cards and banner.

## Goals

- After a cluster-only run completes, request and render `steps/clusters`: an input summary (associated Sessions / problem reports / potential bad cases / clusters), a cluster list ordered by severity, and expandable source bad-case tables, visually reusing the V2 run-detail step-5 cluster cards.
- During `preparing` / `running`, show the preparation stage and poll without requesting the cluster step early; failures and an empty cluster list have explicit states.
- The banner offers "start evolution from these problems →", creating a `mode=full` run with the same condition (target, version, window, potential policy, cache toggle) and navigating to the run detail.
- Backend `_progress()` distinguishes `cluster_only`: five total steps, labels in "clusters and severity", a completed label of "聚类完成", and no iteration turn or 71% progress; the run list card follows.
- Unit tests and E2E lock both "the page really renders cluster content and the launch button" and "a completed cluster-only run does not show iteration", so an empty shell can no longer pass.

## Design authority

- [08 §11 cluster-only page](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#11-仅聚类页pagesevolutionclusterpreviewvue): preparing polling, banner + launch entry, input summary, cluster list with source bad cases, and the `steps/clusters` data channel.
- [02 F12](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/02-features.md): functional boundary and data sources of the cluster-only results page.
- [05 §4.12](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/05-api-design.md): `cluster-previews` launch and `steps/clusters` contract; this issue does not change the contract.
- [V1 baseline prototype renderClusterOnly()](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/14-15-ui-prototype/harness-evolution.html#L3242): title, input summary, cluster cards, and launch button structure.
- [V2 prototype run-detail step 5](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L5423): cluster cards, stats strip, and banner styles; V2 has no standalone cluster-only page, so this page introduces no new visual language.
- [issue #466](https://github.com/Shadow-Azure/harness-evolution/issues/466): production reproduction, screenshot comparison, and root cause.

## Implementation

- `apps/web/src/pages/evolution/ClusterPreview.vue`:
  - Change the header to "问题聚类结果" plus a target chip; keep the back-to-list button.
  - State in the banner that patch generation and evaluation iteration did not run, with "start evolution from these problems →" on the right; disable it while launching and show the failure reason.
  - After completion, read `steps/range` (for the same condition) and `steps/clusters` in parallel; build the input summary from run stats sessions / badCases / potential / clusters and the condition line from the range window, models, and policy.
  - Reuse `components/StepClusters.vue` for the cluster list and add optional title/subtitle props whose defaults keep run-detail step 5 unchanged.
  - Use Chinese status badges; on completion show `progress.stageLabel` (the corrected backend returns the cluster-complete label), and during preparation show "associating Sessions / filtering potential / generating attribution / clustering".
  - "Start evolution" calls `startEvolutionRun` with a body reconstructed from the range condition for target / window / policy / cache, `mode: "full"`, and navigates to `/evolution/runs/{runId}` on 202.
- `apps/api/app/service/evolution/runs.py`: `_progress()` uses `PREPARE_COMPLETE_UNIT` as the total for `cluster_only`, /5 stage labels, "第 5/5 步 · 聚类完成" on completion, and `doneRounds=0`; the seven-step wording for full runs is unchanged.
- `apps/web/src/pages/evolution/components/RunCard.vue`: a completed cluster-only card uses the badge "✓ 已完成 · 仅聚类", replaces "已跑轮次" with "聚类", and shows "仅聚类分析 · 未执行 patch 生成与评测迭代" instead of "终评数据暂不可用".
- Tests:
  - Add a parameterized `cluster_only` progress case to `apps/api/tests/m5-04-run-list/test_runs_service.py` and a `progress_total()` case to `m5-01-evolution-state`.
  - `apps/web/src/pages/evolution/ClusterPreview.test.ts` covers no cluster request during preparation, input summary / cluster cards / source table / deep links after completion, the full-run launch request body and navigation, and the failure state; `RunCard.test.ts` covers the completed cluster-only card.
  - Extend the cluster-only section of `tests/e2e/m11-05-v2-cross-stack.test.mjs`: `.cluster` count, input summary, cluster heading, launch button, source deep link, a status text without iteration, and the list card badge without "已跑轮次".
- Add a `bug-fix` Agent Note recording the choice to keep `cluster_only` and reuse the V2 cluster cards, and why the entry was not removed to match the V2 prototype.

## Implementation steps

1. Fix the `cluster_only` wording in backend `_progress()` and add API unit tests.
2. Add optional title props to `StepClusters.vue`, keeping the run-detail default rendering unchanged.
3. Implement the preparing state, input summary, cluster list, full-run launch, and error state in `ClusterPreview.vue`.
4. Add Web unit tests and m11-05 E2E assertions, and update affected existing assertions.
5. Start the local fixtures + API + Web page and capture same-viewport Before (current main) and After (this branch) evidence, compared with the V1 baseline / V2 step 5 and 08 §11.
6. Write the Agent Note, run focused tests, type checks, lint, docs, and flow gates, and open the PR.

## Dependencies and boundary

- Depends on: m10-04, m10-05 (seven-step preparation and the four-step wizard / cluster-previews are in place).
- Delivery boundary: only the cluster-only page, the cluster-card title props it uses, the run progress projection, and their tests; do not change the clustering algorithm, confidence/severity algorithm, `steps/clusters` contract, run state machine, historical run data, or the existing layouts of the launch wizard and run detail.
- The V2 prototype has no standalone cluster-only page: this page follows 08 §11 and the V1 baseline for structure and reuses the V2 step-5 cluster cards visually; this issue does not remove the "仅聚类" entry.
- Do not write production run ids, Session content, production screenshots, or credentials into the repository; Before/After and smoke screenshots stay in the PR description or local evidence only.

## Verification

```sh
apps/api/.venv/bin/python -m pytest apps/api/tests/m5-04-run-list/test_runs_service.py
pnpm test:web -- ClusterPreview
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- --pattern m11-05
pnpm verify:flow && pnpm verify:docs
```

- A `cluster_only` run card has `progress.total=5`; at unit=5 it has `percent=100`, `stageLabel="第 5/5 步 · 聚类完成"`, and `doneRounds=0`; the existing full-run cases still pass.
- Completed page: inside `[data-testid='evolution-cluster-preview']` the text "问题聚类结果", "输入概况", "聚类出的 N 类问题", and "以这批问题启动自进化" appears; `.cluster` count equals the cluster count from the endpoint; expanding a card shows the source bad-case table.
- The preparing state only polls run detail and does not request `steps/clusters`; that request starts only after completion.
- Clicking launch sends `POST …/evolution/runs` with target, window, policy, and cacheEnabled matching the range condition and `mode="full"`, then navigates to `/evolution/runs/{runId}`.
- The status bar no longer shows "迭代", "第 6/7", or 71%.

## Acceptance

- At the 1500×837 viewport the cluster-only page shows complete cluster content: banner + launch button, the problem-cluster-results title with target chip, input summary, severity-ordered cluster list, and expandable source bad cases; the page can scroll to the last cluster.
- Status badges and stage copy are Chinese; completion shows "第 5/5 步 · 聚类完成", and both the list card and the detail page stop describing a cluster-only run as an iteration.
- "Start evolution from these problems" creates a full run with the same condition and opens its detail; failures show a readable in-page error.
- Run-detail step-5 cluster card headings, current-step rendering, and existing E2E assertions do not regress.
- The PR contains same-scenario, same-viewport, same-theme Before/After screenshots (Before labelled with the baseline commit) plus a comparison note against the V1 baseline / V2 step 5; no production screenshot is committed.
- The proposer gives final acceptance; the fix PR only delivers reviewable implementation and evidence.

## Gates and CI

- API unit tests: `apps/api/.venv/bin/python -m pytest apps/api/tests/m5-04-run-list/test_runs_service.py`; CI runs the full `pnpm test:api`.
- Web: `pnpm test:web -- ClusterPreview`, `pnpm typecheck:web`, `pnpm lint:web`.
- E2E: `pnpm test:e2e -- --pattern m11-05`.
- Flow and docs: `pnpm verify:flow`, `pnpm lint:docs`; the PR title carries `(#<this issue number>)` and references #466.
- Deliver to human review after CI is green; a person merges this PR.

## Non-goals

- Do not remove the "仅聚类" entry, the `cluster-previews` endpoint, or the `evolution/cluster/:runId` route, and do not redirect cluster-only runs to run-detail step 5.
- Do not change clustering input, confidence/severity algorithms, attribution cache, `steps/clusters` fields, or historical run migration.
- Do not refactor the launch wizard, run list, run detail, or global styles; do not add design tokens or a second cluster-card component.
- Do not add a cluster-only entry/page to the V2 prototype (the prototype has none) or modify `plans/ui-prototype-v2/harness-evolution.html`.
