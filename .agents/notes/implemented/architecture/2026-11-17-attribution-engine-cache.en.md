# Agent Note: Object-revision attribution engine, cache, and candidate writes

Status: implemented

English | [中文](2026-11-17-attribution-engine-cache.md)

## Problem

A potential case only means "possibly related to this object". Self-evolution also needs a reusable conclusion scoped to the object revision, distinguishing `attributed`, `non_target`, and not-yet-analyzed cases. V1 collapsed attribution into a 1:1 case status and had no cache key, reuse counter, knowledge evidence, or durable explanation for run details. If the engine reads and writes the database directly, cache hits, concurrent upserts, and failure recovery become entangled with rule logic; if every retry recomputes all candidates, `blocked(attribution)` recovery repeats engine work and overwrites completed conclusions.

## Decision

- Engines are pure functions: `AttributionEngine` receives only an `AttributionInput` (case title/description/metadata, hit reason, both trigger points, knowledge-document evidence, object revision) and returns an `AttributionResult`. The first `rule-v1` engine uses deterministic templates: self report with error evidence → `attributed/error/0.8`; self report without error evidence → `attributed/prompt/0.8`; `after_object` discovery → `attributed/error/0.6`; insufficient evidence or incomparable order → `non_target/None/0.7`.
- The registry only accepts explicit keys: `resolve_attribution_engine` raises `ConfigError` for an unregistered key, and `create_app` validates `HE_ATTRIBUTION_ENGINE` at startup so an unknown engine fails fast. The cache key is bound to the engine key; replacing the model means adding an Engine subclass and registering a new key.
- The cache key remains the seven-part `sha256(workspace_id + bad_case_id + probe_type + probe_object + object_version + policy_version + attribution_engine)`; the `object_version` component uses the resolved `targetRevision`. `probe_reports.object_version` grows from 64 to 96 so `digest:<sha256>` (71 chars) and `tag:` / `provider:` forms need no truncation or hash mapping.
- `AttributionRunner` owns cache and writes: on a hit with `cache_enabled`, it reuses the `probe_id`, increments `reused_count` at most once per run, and marks the candidate `is_cached=true`; with `cache_enabled=false` it skips the read and overwrites the same key, updates `created_run_id`, and leaves the historical reuse count intact. Concurrent same-key writes keep using dialect-specific atomic upserts.
- New repository methods `write_probe_and_link` and `reuse_probe_and_link` complete the probe upsert, the `bad_case_analysis` link, and the candidate `probe_id/is_cached` pointer in **one transaction**; a missing candidate row rolls all three writes back, so no orphan probe survives. The runner skips candidates returned by `linked_probe_ids`, so a failed retry only fills the unfinished tail.
- `non_target` keeps `attribute_type` NULL and retains the probe and link for error-detail reads; `list_clusterable_probe_ids` only projects `included=true` probes whose `conclusion='attributed'`, so clustering never receives non-target or policy-excluded rows.
- Knowledge evidence is batch-loaded per case root Session (`agent_events.kind='knowledge'` document/path/revision/retrieval kind) and enters `rule-v1` reasoning; when a self report has no error field but knowledge-document evidence exists, it is classified as prompt.
- New `evolution_runs.potential_policy / cache_enabled / attribution_engine` snapshot columns default to `NULL / false / legacy-probe-import` for old runs. The `blocked_stage` closed set gains `attribution`, and jobs/events map it to `prepare`; because attribution has no iteration state to resume, `/retry` keeps the "no rounds → enqueue `evolution_prepare`" path, and prepare re-entry skips linked candidates.

## Alternatives considered

- **Engine reads/writes the database**: cache and concurrency logic would leak into rule branches and make model replacement unsafe; rejected, engines stay pure.
- **Truncate or hash the 71-char digest into 64 chars**: this loses revision identity and makes the read model disagree with the cache key; rejected, widen the column to 96.
- **Read `cache_key` before inserting**: concurrent writers collide on the unique key or create duplicates; rejected, keep dialect atomic upserts.
- **Write probe, link, and candidate in three transactions**: a mid-step failure leaves a probe with no candidate pointer and an unclear resume boundary; rejected, use one transaction and roll back when the candidate is missing.
- **Reset `reused_count` when the cache is disabled**: the counter is an audit fact, not part of the current conclusion; rejected, refresh only conclusion fields and `created_run_id`.
- **Recompute every candidate on retry**: this repeats engine work and overwrites completed conclusions; rejected, use the candidate `probe_id` as the completion marker.
- **Feed non_target rows into clustering**: rows without `attribute_type` would pollute clusters and severity; rejected, the repository projects attributed probes only.

## Consequences

- The cache key depends on `attribution_engine` and `targetRevision`; different revisions and engines keep separate rows, and historical conclusions are preserved but never hit by a new engine.
- `rule-v1` is a placeholder; reason/reasoning are template text. It does not claim final model quality or run real LLM ranking.
- Batched attribution events (one `attribution_created/reused` per 20 rows) are left to the m10-04 prepare template; this slice returns `processed/created/reused/non_target/skipped` for it to aggregate.
- `/retry` for `blocked(attribution)` currently covers "resume state + re-enqueue prepare"; the attribution re-entry and state-machine cursor inside prepare belong to m10-04.
- Historical V1 runs keep `attribution_engine='legacy-probe-import'` and are never consumed by the `rule-v1` runner; old probes that cannot compute the seven-part tuple keep `cache_key=NULL` rather than inventing a cache identity.
