# Agent Note: cluster evolution runs from attribution conclusions

Status: implemented

English | [中文](2026-11-24-attribution-clustering.md)

## Problem

Production run `01M86AXB7180YHS9XY6D67KEG0` on 2026-11-24 had 20 `attributed` probes but step 5 produced only 3 clusters whose member counts 13 / 6 / 1 matched the `prompt` / `flow` / `error` categories. Cluster 1 was titled `[SWE-bench] astropy__astropy-13398 · unresolved`, while its 13 members spanned four instances and at least seven mechanisms; the first patch turn therefore changed transport failures, requirement coverage, regression gates, incremental persistence, and the completion template together.

The lexical grouping read `bad_cases.title`. That premise came from m12-04: `rule-v1` conclusions were template sentences whose shared words reached roughly 0.70 across different problems, so a title separated cases better. V2 attributions are real, case-specific model conclusions, but grouping stayed on the title assumption. The SWE-bench adapter emits a fixed title template where the instance number is one token, so any two `unresolved` titles have Jaccard ≥ 0.429 and single-link merge past 0.3. `cluster.review` is merge-only, so the three category drafts could not be corrected. Attribution conclusions only decided whether a probe qualified and which category bucket it entered; they never decided who belongs together.

## Decision

- The grouping signal is the attribution conclusion: every `attributed` probe becomes a one-probe draft built from its `probe_reports.probe_description`, bounded to 240 characters, and the lexical layer stops merging titles.
- `cluster.review` keeps its task key and `{"from": [...]}` output contract, but its semantics change from merging lexical drafts to merging one-probe drafts by shared root cause. The prompt forbids instance name, dataset prefix, title template, or category as a shared root cause; the same root cause may merge across instances and different root causes must stay apart even with identical titles.
- Degradation produces one bucket per category described as `{type} issues · {N} attributions (clustering degraded)`, never N one-probe clusters and never a fabricated root-cause description.
- Review input above `ATTRIBUTION_REVIEW_MAX_DRAFTS = 200` is reviewed in category batches, each a complete partition; batching records one `degraded` item while the normal path remains one review call.
- The algorithm identity becomes `hybrid-attribution-llm-v1`; `hybrid-lexical-llm-v1` remains for reading old runs and the no-agent legacy path.
- The step-5 cluster title is derived from the cluster description, not the first member's bad-case title. The table and scoring path are unchanged.
- Under attribution grouping, `signature_overlap` is no longer recomputed from titles and stays a zero statistic; titles are no longer a grouping or compactness signal.

## Alternatives considered

- **Tune `SIMILARITY_THRESHOLD` only**: title Jaccard bottoms out at 0.429 while conclusion Jaccard tops out at 0.178; threshold changes only move between "merge everything" and "one draft per probe", not a root-cause partition.
- **Swap the field and keep lexical merging**: conclusion similarity is too low for lexical merge; a threshold around 0.12 chains unrelated mechanisms, so semantic merging has to happen in the review layer.
- **Let review split drafts**: that breaks the O(K) output invariant and the one-to-one input/output keys; merge-only stays auditable.
- **Group by category or instance directly**: a category is a 5-value coarse class and an instance is a dataset identity, not an actionable root cause; this is exactly the failed production result.
- **Introduce embedding/vector search**: it can improve recall but needs new infrastructure and configuration, and still cannot replace the "one fix covers every member" judgement; left as an optional later upgrade.
- **Persist N singleton clusters after review failure**: that turns every attribution into its own turn with unacceptable cost and noise; category buckets with an explicit degraded label are more honest.

## Consequences

- `cluster.review` input grows from O(K) to O(N), about 6k tokens for N=20, still one call. The cap and batching keep the prompt bounded, at the price of no cross-batch root-cause merges.
- Clustering quality depends on the conclusions and the review model. This decision guarantees that the grouping signal is the attribution conclusion and that the partition is validatable; it does not promise accuracy.
- Old `hybrid-lexical-llm-v1` runs keep their step reads and historical hashes. New runs record the algorithm identity, draft count, and truncation policy in `clusters_created` for replay.
- The no-agent legacy lexical path remains for tests and offline callers; production assembly always binds a provider, so production's default path is attribution grouping.
- The frontend no longer copies the first member's case title as the cluster title; the degraded wording explicitly says clustering degraded so a category bucket is not mistaken for a root-cause cluster.
