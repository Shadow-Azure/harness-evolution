# Agent Note: V2 design docs — workspaces, overview, and attribution inside evolution

Status: proposed

English | [中文](2026-11-11-v2-design-docs.md)

## Problem

The V2 prototype (`plans/ui-prototype-v2/`) establishes four new capability classes: multi-user login with a reserved auth integration seam, multi-workspace bad-case ingestion with quotas, a workspace overview, and attribution moved into the self-evolution flow. The fullstack-design docs still describe the V1 target state: D10 declares a single shared organization with no row-level isolation, evolution input treats external `probe_reports` as its only source, the error detail page carries exactly one attribution per bad case, and nothing defines an overview, workspaces, or an ingest API. Building straight from the prototype would leave implementation guidance contradicting the docs — the issue body contract requires design references into `plans/fullstack-design` sections, and those sections win on conflict.

A second decision had to come first: the current implementation already matches the V1 design closely (endpoints and all twenty tables verified item by item). Rewriting the V1 docs in place would mix "implemented and frozen V1 behavior" with "not-yet-implemented V2 goals" in the same statements, leaving readers unable to tell which is which.

## Decision

Merging the V2 design into docs 01–08 by domain instead of adding addenda: workspaces/auth/ingest land in [01 §1/§4.4](../../../../plans/fullstack-design/01-architecture.md), [05 §3.7/§4.16–§4.17](../../../../plans/fullstack-design/05-api-design.md), [06 §3.10–3.12](../../../../plans/fullstack-design/06-database-design.md), [07 §5.15/§8.2.1](../../../../plans/fullstack-design/07-backend-implementation.md) and [08 §4.2](../../../../plans/fullstack-design/08-frontend-implementation.md); the overview and session list land in [05 §3.10/§4.18](../../../../plans/fullstack-design/05-api-design.md), [06 §7.5](../../../../plans/fullstack-design/06-database-design.md) and [08 §5.2.1/§6](../../../../plans/fullstack-design/08-frontend-implementation.md); attribution and the seven-step flow land in [05 §3.6/§4.19–§4.20](../../../../plans/fullstack-design/05-api-design.md), [06 §4.2/§5.3–5.4/§5.9](../../../../plans/fullstack-design/06-database-design.md), [07 §5.11–5.14](../../../../plans/fullstack-design/07-backend-implementation.md) and [08 §7/§9/§10](../../../../plans/fullstack-design/08-frontend-implementation.md). The README decision table gains D21–D23, and [15](../../../../plans/fullstack-design/15-v1-v2-gap-analysis.md) records implementation gaps and the code-change map.

Key trade-offs: the workspace session set is a projection over the workspace's bad cases and trace tables gain no workspace column; auth integration collapses into an AuthProvider protocol plus a session bridge plus a stub callback while the identity stack itself is unchanged; `bad_case_analysis` drops its case uniqueness and becomes a many-attribution link table, while `probe_reports` gains `cache_key`, conclusion, and reuse fields in place with `probe_id` mapped to `attributionId`; `probe_clusters` and `probe_cluster_probes` keep their original names; trigger-point comparison prefers `agent_events.triggered_at` with a `(agents.tree_index, event_index)` fallback and uses `object_version` when present; the candidate table persists every row including policy-excluded ones so run details stay explainable.

## Alternatives considered

- Rewriting docs 01–08 wholesale into the V2 target state: it would interleave implemented V1 behavior with unimplemented V2 goals across six large documents at high review cost; addenda plus freeze markers keep both generations traceable.
- Extending `plans/ui-prototype-v2/design-v2.md` into the implementation design: that file is a prototype acceptance note with no database/API/implementation layers and sits outside the fullstack-design reference graph, so issues could not link it per their body contract.
- Adding `workspace_id` to the trace side (session_families/agents): normalization is a global pipeline and a session can legitimately be reported by several workspaces; requiring ownership before ingestion would complicate reporting for no benefit.
- Appending one attribution row per run and querying the latest: pagination and "reuse the most recent result" would both need a second dedup pass; upserting by cache key plus reuse counters keeps the cache semantics and paginated query direct.
- Migrating `analyzed_nonissue` to `non_target`: the predicates differ (the former negates the bad case itself, the latter only the object attribution), so migration would falsify history.
- Keeping `POST /api/evolution/probes/query` for a compatibility window: the new wizard uses the three preview endpoints, while the old endpoint stays deprecated and outside V2 page code.

## Consequences

V2 implementation issues can slice directly along the code-change maps in [15 §6–§7](../../../../plans/fullstack-design/15-v1-v2-gap-analysis.md) (workspace tables and permissions → ingest → overview → trigger-point columns → wizard/pipeline → error detail), each with an explicit design reference. The frontend receives one seven-step DTO; the server adapts legacy V1 runs instead of maintaining two component schemas. `agents.tree_index`, `agent_events.triggered_at`, and `agent_events.object_version` only reach existing data after a parser-version bump and replay, so that slice must land before potential matching. The overview "potential" count shares one PotentialMatcher with the wizard and runs behind a 60-second cache, guarded by consistency regression cases. Historical events without object versions never create a Session association and are counted as `versionUnresolvedSessions`; `/api/probes/*` and `/analysis` remain compatibility endpoints during deprecation.
