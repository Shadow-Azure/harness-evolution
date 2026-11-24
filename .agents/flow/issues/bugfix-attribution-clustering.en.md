# Cluster evolution runs by attribution conclusions, not bad-case titles

English | [中文](bugfix-attribution-clustering.md)

```yaml flow
kind: issue
id: bugfix-51
milestone: bugfix
depends:
  - bugfix-19
priority: P2
status: in-progress
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/db/crud/attributions.py
  - apps/api/tests/**
  - apps/web/src/**
  - tests/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/architecture/2026-11-24-attribution-clustering.md
github:
  number: 587
  url: https://github.com/Shadow-Azure/harness-evolution/issues/587
```

## Background

Production run `01M86AXB7180YHS9XY6D67KEG0` produced only 3 clusters from 20 `attributed` probes. The member counts 13 / 6 / 1 matched the `attribute_type` buckets `prompt` / `flow` / `error` exactly. Cluster 1 was titled `[SWE-bench] astropy__astropy-13398 · unresolved`, while its 13 members actually spanned four instances (`13398` / `13236` / `12907` / `13033`) and at least seven root-cause mechanisms. The first patch turn therefore changed transport failure recovery, requirement coverage, regression gates, incremental persistence, and the completion template at once.

The grouping signal was wrong: `prepare._build_clusters` fed bad-case titles into `cluster_probes`, and the SWE-bench adapter emits a fixed title template, so any two `unresolved` titles have Jaccard ≥ 0.429 and single-link merge past the 0.3 threshold. `cluster.review` is merge-only, so it could not split the three category drafts afterwards. Attribution conclusions were used only for admission and display, never for grouping.

## Goals

- Default grouping becomes one draft per attribution conclusion: `probe_reports.probe_description` is the only grouping text and the lexical layer stops merging titles.
- `cluster.review` merges one-probe drafts by shared root cause; title/description come from the conclusions, and merging by instance name, dataset prefix, title template, or category is forbidden.
- Degradation produces one bucket per category and records `degraded`; it never persists N one-probe drafts as N clusters.
- Inputs above the review cap are reviewed in category batches, each a complete partition, with the batching fact recorded in `degraded` instead of silently reverting to title clustering.
- The algorithm identity becomes `hybrid-attribution-llm-v1`; old `hybrid-lexical-llm-v1` runs keep their read behavior.

## Design authority

- [07 §5.5 grouping layer](../../../plans/fullstack-design/07-backend-implementation.md): grouping features and description generation.
- [07 §5.5.2 three layers](../../../plans/fullstack-design/07-backend-implementation.md): draft-key references, merge-only review, failure policy, and cost shape.
- [06 §5.3 probe_clusters](../../../plans/fullstack-design/06-database-design.md): cluster and member persistence stays unchanged.
- [08 §11 run detail](../../../plans/fullstack-design/08-frontend-implementation.md): step-5 cluster card and source bad cases.
- [Attribution clustering Agent Note](../../notes/implemented/architecture/2026-11-24-attribution-clustering.en.md): this decision and its alternatives.

## Implementation

- `AttributionRepository.list_clusterable_probes` returns `ClusterableProbe(probe_id, attribute_type, bad_case_id, probe_description)`, so grouping does not need a second query.
- `cluster.build_attribution_drafts` renders one draft per attribution in `TYPE_ORDER` and `probe_id` order, bounded to 240 characters; an empty conclusion gets a unique honest fallback instead of merging unrelated probes.
- `cluster_llm.build_review_request` gains `grouping="attribution"`: summaries are conclusions, merging requires that one fix covers every member, and instance/template/category are explicitly rejected as shared root causes.
- `enhance_clusters` gains `grouping`: attribution fallback merges by category with `{type} issues · {N} attributions (clustering degraded)`; `signature_overlap` is no longer recomputed from titles.
- Above `ATTRIBUTION_REVIEW_MAX_DRAFTS` the review runs in category batches, each a complete partition; batching records one `degraded` item while the normal path stays a single review call.
- `prepare._build_clusters` uses the new path; `clusters_created` adds `draftCount`, `draftSummaryMaxChars`, and `grouping`; `stages._cluster_item` derives the cluster title from the root-cause description instead of `cases[0].title`.
- The step-5 subtitle and prototype copy change to "cluster by attribution root cause".

## Implementation steps

1. Extend the attribution repository projection with the conclusion text.
2. Add the one-probe draft builder and the attribution review prompt.
3. Change fallback batching, algorithm identity, and event payload.
4. Change the step-5 title source and frontend copy.
5. Add unit tests, a production-shaped 20-attribution regression, docs, and the Agent Note.

## Dependencies and boundary

- Depends on bugfix-19 (the three-layer clustering baseline and `hybrid-lexical-llm-v1`).
- Boundary: only the grouping layer, read projection, related contracts, tests, frontend copy, and docs. No `probe_clusters` / `probe_cluster_probes` schema change, no patch/evaluation/push change, no embedding.
- Out of scope: cross-category root-cause merges, a new `root_cause_key` on attribution, historical run recomputation, and any accuracy promise for the model.

## Verification

```sh
pnpm test:api -- tests/evolution/test_cluster_attribution_drafts.py
pnpm test:api -- tests/test_clustering_three_layers.py tests/m12-04-clustering-upgrade tests/evolution/test_m10_04_prepare.py
pnpm verify:flow
pnpm verify:docs
```

- 20 attributions produce 20 one-probe drafts with a 13 / 6 / 1 type split; no two are merged by their shared title.
- A valid review output covers every draft key exactly once; same root causes may merge and different ones stay apart; descriptions differ from member titles.
- A failed review persists only 3 category buckets with the degraded wording; `strict` writes no clusters and fails the run.
- An oversized input is batched by category, `degraded` records it, and cluster members still cover every probe.
- Old `hybrid-lexical-llm-v1` runs keep their step reads.

## Acceptance

- The `prompt` category no longer becomes one cluster; 13 same-template titles split by root cause and no cluster mixes two different root causes from different instances.
- Every `attributed` probe appears exactly once in cluster membership; `non_target` never enters a cluster.
- Step 5 no longer titles a cluster with the raw `[SWE-bench] ...` title and no description claims a signature count that contradicts its members.
- Clustering still goes through `ClaudeCodeProvider.analyze` + `StructuredSubmission`; no new LLM client.
- `clusters_created` and `/steps/clusters` expose the algorithm, draft count, and degradation reason; the UI labels degraded clustering.

## Gates and CI

- api-static / unit-tests-api / web-tests / docs-flow / flow.
- New unit tests cover the 20-attribution regression, category fallback, batching, and descriptions that differ from member titles.
- Commit and PR titles carry `(#587)`.

## Non-goals

- No embedding/vector store and no `root_cause_key`.
- No historical run recomputation and no schema change.
- No change to patch generation, evaluation, push, or acceptance rules.
