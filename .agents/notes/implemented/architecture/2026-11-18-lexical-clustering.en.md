# Agent Note: Deterministic lexical clustering replaces placeholder halves

Status: implemented

English | [中文](2026-11-18-lexical-clustering.md)

## Problem

Step five of the evolution flow used a V1 clusterer that sorted probes by category and split them in half. Cluster membership had no relation to the reports' meaning; it only kept the seven-step flow runnable. M12 asks for a real clustering algorithm while keeping `probe_clusters` / `probe_cluster_probes`, API fields, and scoring semantics unchanged, with deterministic behavior for empty, single, duplicate, and large inputs.

Clustering directly on `probe_reports.probe_description` does not work: the `rule-v1` conclusion is a template sentence ("object self-report: …; no error evidence, classified as prompt"). Two different problems can reach 0.70 similarity just by sharing template words, which drowns out the case-specific signal.

## Decision

- The clustering feature is the bad case title `bad_cases.title`: it is the reporter's problem summary and separates cases better than a templated attribution reason. The title is read-only loaded from the external problem table with the candidates.
- Each `attribute_type` is clustered independently. Text becomes a set of ASCII word tokens and CJK character bigrams; two sets with Jaccard ≥ `0.3` are considered similar. Similarity uses single-link connected components, so members are no longer cut in half by count.
- Blank text never merges and stays in its own singleton cluster; duplicate `probe_id` rows are first deduplicated by `(attribute_type, text)`. Clusters and members are ordered by `probe_id`, empty input yields no clusters, so the same input always produces the same output regardless of database row order.
- A cluster description is `"{type} 类问题 · {title of the smallest probe_id in the cluster}"`; the title is whitespace-normalized and truncated to 120 characters, with a member-count fallback when no title exists.
- The algorithm identity `CLUSTER_ALGORITHM = "lexical-jaccard-v1"`, the threshold, and the cluster result hash are written into the `clusters_created` event payload as run-level reproduction parameters.
- Write paths, tables, links, and scoring formulas stay unchanged: the code still writes `probe_clusters` / `probe_cluster_probes`, and `confidence`, `impact`, `severity`, and `rank` still follow [06 §5.3](../../../../plans/fullstack-design/06-database-design.md).

## Alternatives considered

- **Keep splitting by count**: simplest to implement, but cluster membership stays unrelated to meaning and the M12 algorithm upgrade is not delivered; rejected.
- **TF-IDF/cosine over the attribution reason**: template words are shared heavily by the rule engine, and two different problems measured about 0.70 similarity; switching to the title removes the template noise.
- **k-means with a fixed k**: requires a prior cluster count; forcing unrelated problems together changes the severity/turn semantics and exceeds this issue's independently verifiable boundary.
- **Vector models or an external clustering service**: would add dependencies, external resources, and deployment configuration, while this issue must be verifiable without schema changes or new resources; left for a later real-service replacement.
- **Keep the old `simple_cluster` as a comparison baseline**: clusters of historical runs are already persisted and need no recomputation; keeping dead production code would leave two long-lived algorithm contracts. The before/after behavior is instead expressed by an upgrade test.

## Consequences

- The cluster count is no longer limited to two per category; one turn maps to one cluster, so more scattered problems mean more turns. This is the cost of finer-grained clustering; bounding turns would require a separate issue on scheduling policy.
- Lexical similarity is not semantic equivalence; title language and length affect the result. This issue makes no accuracy claim about the diagnosis. The algorithm version and threshold are stored in the run events so results can be reproduced and later replaced.
- The `m5-01` placeholder clustering test is removed with the algorithm; `tests/m12-04-clustering-upgrade` covers similar/unrelated titles, threshold boundary, empty input, a single element, duplicate input, blank titles, large input, and prepare persistence.
