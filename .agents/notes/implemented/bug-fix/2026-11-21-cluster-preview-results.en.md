# Agent Note: Cluster-only page reuses V2 cluster cards and reclaims cluster-step progress

Status: implemented

English | [中文](2026-11-21-cluster-preview-results.md)

## Problem

A cluster-only run's core output is already returned by `GET /runs/{rid}/steps/clusters`, but `ClusterPreview.vue` has rendered only the banner, run title, status bar, and target/window since m5-05, leaving the page blank. `_progress()` also uses the full seven-step `total_units()` and seven-step labels for every mode, so a completed run at `unit=5` is described as "step 6/7 · iteration", contradicting the rule in `state.py` that hides `iteration/final` for `cluster_only`. [issue #466](https://github.com/Shadow-Azure/harness-evolution/issues/466) records the production screenshot, the same-code reproduction, and the root cause.

The real tension is product direction: the V2 prototype has no cluster-only page and no wizard exit for it, so removing the entry looks plausible. But feature list [02 F12](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/02-features.md) and [08 §11](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#11-仅聚类页pagesevolutionclusterpreviewvue) still define the page as a real capability, and the V1 baseline prototype has a complete page. Production keeps the entry, route, and `cluster-previews` endpoint, so deleting it would shrink an already promised capability.

## Decision

- Keep the `cluster_only` capability and complete the page per 08 §11 / the V1 baseline: input summary, severity-ordered cluster list, expandable source bad cases, and "start evolution from these problems →" inside the banner. Do not invent a second visual language: reuse the V2 run-detail step-5 cluster cards and banner styles; add optional title/subtitle props to `StepClusters.vue` while keeping the run-detail defaults.
- Do not trust front-end caches for "start evolution": after completion, read `steps/range`, `steps/clusters`, and `steps/attribution` in parallel and rebuild the `mode=full` request from the range's persisted condition snapshot (target, version, window, policy, cache). The attribution `badCaseId → sessionId` map is only used to deep-link source bad cases, so a stale run card or list cache cannot launch with different conditions.
- Visible progress belongs to `state.py`: add `progress_total(mode, cluster_count)`, which returns the fixed five units for `cluster_only`. `_progress()` uses it for total/percent, emits /5 labels, and writes "第 5/5 步 · 聚类完成" on completion with `doneRounds=0` and `accepted=0`. The seven-step wording for full runs is unchanged.
- The run card follows the mode: a completed cluster-only card uses the badge "✓ 已完成 · 仅聚类", replaces "已跑轮次" with the cluster count, and states that iteration/final evaluation did not run; full-run cards are unchanged.
- The page root owns scrolling per the bugfix-01 convention: `height: 100%; overflow-y: auto`, so 1500×837 can reach the last cluster; at ≤640px the document scrolls instead.

## Alternatives considered

- **Remove the cluster-only entry, route, and `cluster-previews` to match the V2 prototype**: this removes the "entry without a design target" gap, but 02 F12 and 08 §11 still list the page as a real feature; deleting it breaks the delivered API, historical `cluster_only` runs, and the user entry point. Rejected until product direction is confirmed; no destructive contraction.
- **Keep the seven-step total for `cluster_only` and only reword unit=5**: the label stops mentioning iteration, but the progress bar still has seven slots and can still show 71%, and the list card and detail page keep disagreeing. Rejected; total must share the same source as the visible steps.
- **Create a second cluster-card component for the cluster-only page**: the page structure differs, but rank/category/confidence/severity would have two implementations that drift on the next style change; `StepClusters` already covers the fields. Rejected in favour of optional heading props.
- **Build the launch condition from the run card**: the card only has the policy preset, not the custom switches, so `mode=full` would silently use a different policy; the range step is the persisted condition snapshot. Rejected.

## Consequences

- The completed cluster-only list card and detail page both show "第 5/5 步 · 聚类完成", with no iteration turn or 71%; `GET /runs/{rid}` returns `progress.total=5` for `cluster_only`.
- Run detail still returns seven step nodes for `cluster_only` (iteration/final pending), because the seven keys are a shared contract; that run's detail page is not this entry point and does not render the pending nodes.
- The V2 prototype still has no cluster-only page: structure follows 08 §11 / the V1 baseline and visuals follow V2 step 5. If the prototype later adds the page, it should align with this page rather than the production capability being removed.
- The page adds its own scroll container; if the workspace shell later changes the scrolling contract, `ClusterPreview` and `RunDetail` must change together.
- `ClusterPreview.test.ts` (no cluster request while preparing, summary/cards/source table after completion, launch body and navigation, failure state) and m11-05 E2E (real browser assertions for cards, input summary, launch button, and a status without iteration) lock the regressions; an empty shell can no longer pass.
