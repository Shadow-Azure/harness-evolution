# Agent Note: Paged attribution reads and deep-link detail

Status: implemented

English | [中文](2026-11-17-attribution-read-api.md)

## Problem

A bad case can link several `probe_reports` rows through `bad_case_analysis`, but the API only exposed one inline `analysis` and the probe read endpoints. Error detail could neither page object/revision attributions nor restore one conclusion from an `at` deep link. Reusing `ProbeReport` would make the probe a product concept again, and counting link rows would report three attributions of the same object version as three object versions. Reads also have to prove the case belongs to the caller's workspace first, so a cross-case attributionId cannot leak.

## Decision

- Add `GET /api/workspaces/{wid}/bad-cases/{badCaseId}/attributions?page=&pageSize=` and `.../attributions/{attributionId}` on the existing workspace `problems.py` router with `require_workspace_role(viewer)`. Lists order by `probe_reports.updated_at DESC, probe_id DESC`; `pageSize` defaults to 2 and accepts 1..50; `total` counts only links that project into an `AttributionItem` (inner join to probes) and stays separate from the object/revision count.
- Case existence is decided by the `bad_cases.workspace_id` scope before any attribution read: unknown or out-of-workspace case → `404 BAD_CASE_NOT_FOUND`; an attributionId not linked to that case → `404 ATTRIBUTION_NOT_FOUND`. attributionId maps directly to `probe_id`.
- `BadCase` gains `attributionCount` and `hasAttribution`, fixed to the 06 §4.2.1 distinct `(probe_type, probe_object, object_version)` triple. `service/bad_cases` computes it from the snapshot's analysis and probe rows at the external read boundary, with no new column and no extra query. The V1 inline `analysis` stays during the compatibility window and retires in V3 so the m11-02 frontend switch does not break the old page; conditions live in [compatibility.en.md](../../../../docs/compatibility.en.md).
- `AttributionDetail` adds `reason`, `reasoning`, `policyVersion`, `attributionEngine`, `triggerCompare`, and fixed-text `warnings` as the issue requires. `runId` prefers `last_reused_run_id`; `isCached` means that id is present. `versionState` is `exact|unknown` solely by whether an object version is pinned.
- `triggerCompare` uses the newest candidate linked to the probe: compare wall-clock times when both sides carry one, otherwise compare `(tree_index, event_index)`; a candidate with `order_state=unknown` or missing coordinates stays `unknown` and never claims "after". The candidate's prepare-time `order_state` is authoritative; the service only applies the same display rule.
- Trigger-evidence gaps surface as fixed codes: `ATTRIBUTION_VERSION_UNKNOWN`, `ATTRIBUTION_TRIGGER_UNKNOWN`, `ATTRIBUTION_LEGACY_IMPORT`, `ATTRIBUTION_RUN_UNKNOWN`. Messages never interpolate external fields, so drifted rows cannot leak content through the warning channel.
- Compatibility is unchanged: `/api/bad-cases/{id}/analysis`, `/api/sessions/{sid}/probes`, and `/api/probes/{id}` keep reading the same tables; `/probes/{id}` keeps `probeId` as the attributionId compatibility alias.

## Alternatives considered

- **Return `ProbeReport` as the attribution**: it re-elevates the probe to a product concept and lacks `conclusion`, `isCached`, and `triggerCompare`; rejected.
- **Use link rows as `attributionCount`**: cached reuse of one object version would count as several object attributions, violating 06 §4.2.1; rejected.
- **Count `probe_id IS NULL` V1 rows in `total`**: those rows cannot project an attributionId, so pages and totals would disagree; rejected, keep the inner join.
- **Derive `triggerCompare` from timestamps only**: candidates allow coordinate comparison when `triggered_at` is missing; time-only would downgrade comparable evidence to unknown; rejected.
- **Drop `BadCase.analysis` now**: the m11-02 frontend has not switched yet, so error detail would break; rejected, defer to the V3 retirement.
- **Add a new attribution table or id**: it cuts the `probe_id` chain shared with cache, cluster members, and legacy probe reads; rejected.

## Consequences

The file writer derives a deterministic digest from the Session, selected target identity and version, and bad case ID so the frozen writer can reproduce it. Reads use the complete stored `probe_id` to resolve historical composite IDs to their original reports.

- m11-02 can page a case's attributions and restore detail from `at`; list and detail share one `probe_id`.
- `attributionCount` stays a query-time aggregate and does not change with cache hits or reuse; link rows only affect the page `total`.
- Historical rows without an object version explicitly return `versionState=unknown` plus `ATTRIBUTION_VERSION_UNKNOWN`; clients must not claim an exact revision hit.
- `BadCase` temporarily carries both the inline `analysis` and the counts; the V3 retirement only removes the field and keeps the read rule.
- A new `ATTRIBUTION_NOT_FOUND` code returns 404 for cross-case and cross-workspace reads without leaking existence.
