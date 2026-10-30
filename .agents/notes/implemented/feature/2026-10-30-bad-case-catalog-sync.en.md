# Agent Note: Scheduled catalog sync for bad_cases

Status: implemented

English | [中文](2026-10-30-bad-case-catalog-sync.md)

## Problem

`bad_cases` was treated as data already present in the database: this service only read it while an external system wrote it in place. Once upstream moved to a paginated query API, the problem list, error detail, and root-session trace backfill all lost their data source; m6-15 only backfills root traces and does not ingest bad_cases.

## Decision

Add a single-row `bad_case_catalog_sync` cursor table and a scheduled job of the same name: run once at startup when the previous run finished, then on the configured interval, single-flight and serial. Paging uses the `bad_case_id` cursor with `offset` fixed at 0 and a page size of 200; each page upserts all items and advances the cursor, `synced_count`, and `pending_count` in one transaction, rolling the whole page back on failure. The cold-start cursor starts at 0, so the first run re-pulls the catalog and updates existing ids. The frontend shows four sections in the "data sync" popover: problem counts, problem traces, session normalization, attribution analysis; attribution only aggregates `bad_case_analysis` and does not implement the workflow.

## Alternatives considered

- Offset paging: new inserts shift later pages and make crash recovery ambiguous; cursor paging is independently re-entrant per page and resumes from the last committed page.
- Row-by-row select-then-write: races with external writers; dialect-native `ON CONFLICT DO UPDATE` / `ON DUPLICATE KEY UPDATE` overwrites atomically.
- Cold start from the largest local id: saves the first-run calls but never exercises the update path on rollout; starting at 0 and spreading the work across ticks through page size, max pages, and a time budget is preferred.
- Materializing attribution progress: problem-side data changes upstream, so a stored value goes stale; two COUNT aggregates run at read time instead.
- Reusing `HE_SESSION_QUERY_*`: the two services may use different tokens and versions; a separate `HE_BAD_CASE_QUERY_*` namespace is added.

## Consequences

The change adds a service-owned table, a migration, a job kind, configuration, and three status blocks; `bad_cases` moves from external-write only to external write plus idempotent catalog sync by primary key, while related tables stay read-only. The API only returns `id > cursor`, so content changes on older ids are invisible, and upstream deletions get no tombstone. CI never calls the real upstream; integration and smoke runs use a mock service.
