# Agent Note: V2 design docs — workspaces, overview, and attribution inside evolution

Status: proposed

English | [中文](2026-11-11-v2-design-docs.md)

## Problem

The V2 prototype (`plans/ui-prototype-v2/`) establishes four new capability classes: multi-user login with a reserved auth integration seam, multi-workspace bad-case ingestion with quotas, a workspace overview, and attribution moved into the self-evolution flow. The fullstack-design docs still describe the V1 target state: D10 declares a single shared organization with no row-level isolation, evolution input treats external `probe_reports` as its only source, the error detail page carries exactly one attribution per bad case, and nothing defines an overview, workspaces, or an ingest API. Building straight from the prototype would leave implementation guidance contradicting the docs — the issue body contract requires design references into `plans/fullstack-design` sections, and those sections win on conflict.

A second decision had to come first: the current implementation already matches the V1 design closely (endpoints and all twenty tables verified item by item). Rewriting the V1 docs in place would mix "implemented and frozen V1 behavior" with "not-yet-implemented V2 goals" in the same statements, leaving readers unable to tell which is which.

## Decision

Merging the V2 design into docs 01–08 by domain instead of adding addenda: workspaces/auth/ingest land in [01 §1/§4.4](../../../../plans/fullstack-design/01-architecture.md), [05 §3.7/§4.16–§4.17](../../../../plans/fullstack-design/05-api-design.md), [06 §3.10–3.12](../../../../plans/fullstack-design/06-database-design.md), [07 §5.15/§8.2.1](../../../../plans/fullstack-design/07-backend-implementation.md) and [08 §4.2](../../../../plans/fullstack-design/08-frontend-implementation.md); the overview and session list land in [05 §3.10/§4.18](../../../../plans/fullstack-design/05-api-design.md), [06 §7.5](../../../../plans/fullstack-design/06-database-design.md) and [08 §5.2.1/§6](../../../../plans/fullstack-design/08-frontend-implementation.md); attribution and the seven-step flow land in [05 §3.6.2/§4.19–§4.20](../../../../plans/fullstack-design/05-api-design.md), [06 §5.8–5.10](../../../../plans/fullstack-design/06-database-design.md), [07 §5.11–5.14](../../../../plans/fullstack-design/07-backend-implementation.md) and [08 §7/§9/§10](../../../../plans/fullstack-design/08-frontend-implementation.md). The README decision table gains D21–D23, and V1 behavior is marked frozen throughout.

Key trade-offs: the workspace session set is a projection over the workspace's bad cases and trace tables gain no workspace column; auth integration collapses into an AuthProvider protocol plus a session bridge plus a stub callback while the identity stack itself is unchanged; attributions land in `bad_case_attributions` with one row per cache key (workspace + bad case + object identity + version + policy version + attribution engine) and reuse counters rather than per-run rows; trigger-point comparison prefers `agent_events.triggered_at` with a `(agents.tree_index, event_index)` lexicographic fallback; the candidate table persists every row including policy-excluded ones so run details stay explainable; `bad_case_analysis`, `probe_reports`, and `probe_cluster_probes` freeze read-only, and `analyzed_nonissue` is not migrated (a different predicate from "not this object's problem").

## Alternatives considered

- Rewriting docs 01–08 wholesale into the V2 target state: it would interleave implemented V1 behavior with unimplemented V2 goals across six large documents at high review cost; addenda plus freeze markers keep both generations traceable.
- Extending `plans/ui-prototype-v2/design-v2.md` into the implementation design: that file is a prototype acceptance note with no database/API/implementation layers and sits outside the fullstack-design reference graph, so issues could not link it per their body contract.
- Adding `workspace_id` to the trace side (session_families/agents): normalization is a global pipeline and a session can legitimately be reported by several workspaces; requiring ownership before ingestion would complicate reporting for no benefit.
- Appending one attribution row per run and querying the latest: pagination and "reuse the most recent result" would both need a second dedup pass; a single row of truth plus reuse counters keeps the cache semantics and the paginated query direct.
- Migrating `analyzed_nonissue` to `non_target`: the predicates differ (the former negates the bad case itself, the latter only the object attribution), so migration would falsify history.
- Keeping `POST /api/evolution/probes/query` for a compatibility window: production has no data and no consumers, so removing it and regenerating contracts is cleaner.

## Consequences

V2 implementation issues can slice directly along the code-change maps in docs 15/16/17 (workspace tables and permissions → ingest → overview → trigger-point columns → wizard/pipeline → error detail), each with an explicit design reference. The frontend must render old and new run steps side by side (keyed by `steps_schema`), with the old components frozen until legacy runs age out. `agents.tree_index` and `agent_events.triggered_at` only reach existing data after a parser-version bump and replay, so that slice must land before potential matching. The overview "potential" count shares one PotentialMatcher with the wizard and runs behind a 60-second cache, guarded by consistency regression cases. Remaining debts: object "appearance" in a session is matched by object name rather than version (agent_events carry no version) until upstream traces provide version info, and `/api/probes/*` plus `/analysis` enter a deprecation window before removal next major version.
