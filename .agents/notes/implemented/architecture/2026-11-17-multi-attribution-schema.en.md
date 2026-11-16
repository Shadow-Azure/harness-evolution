# Agent Note: Multi-attribution, cache, and candidate snapshots

Status: implemented

English | [中文](2026-11-17-multi-attribution-schema.md)

## Problem

V1's `bad_case_analysis` used `UNIQUE(bad_case_id)` to collapse each case into one 1:1 status row; V2 needs several attributions per case across objects and versions while preserving the legacy probe read chain and the existing table names. `probe_reports` only stored object detail: no workspace, conclusion, cache, or reuse columns, so a run could not explain which cases entered the potential set, which were excluded, and whether a cache hit occurred. A parallel attribution table would break the `probe_id` compatibility chain, while forcing historical `nonissue` markers and empty `probe_id` values into NOT NULL semantics would delete or fabricate V1 rows.

## Decision

- Evolve in place: drop `uq_bad_case_analysis_case` and add `UNIQUE(bad_case_id, probe_id)`; `analysis_status` becomes nullable, V2 rows leave `analysis_status`/`analysis_result` empty, and `probe_reports.conclusion` is the single source of truth. `probe_id` and `cache_key` stay nullable: V1 `unanalyzed`/`analyzed_nonissue` rows may have no probe, and an orphan probe cannot produce a cache key; the V2 repository writes both as required. The exception is recorded in design 06 §4.2/§9 and tightens during M11 compat retirement. `object_version` also stays nullable, and historical empty values are not backfilled with a fabricated version.
- The cache key is exactly `sha256(workspace_id + bad_case_id + probe_type + probe_object + object_version + policy_version + attribution_engine)`, with a fixed field order and an empty string for a missing version. Workspace and case are inside the key, so cross-workspace and cross-case collisions cannot occur; `probe_id` remains the stable attribution id and is reused on a hit.
- Same-key writes use dialect-atomic statements: SQLite `on_conflict_do_update(index_elements=[cache_key])` and MySQL `on_duplicate_key_update`; no read-before-write. On conflict the original `probe_id`/`created_at` win while conclusion, description, engine, `created_run_id`, and `updated_at` are refreshed. A cache hit calls `reuse()` to bump `reused_count`, write `last_reused_run_id` and `updated_at`, and never inserts another row.
- `evolution_run_candidates` stores the full snapshot: rows with `included=false` are persisted with both trigger coordinates, `order_state`, `included_reason`, `probe_id`, and `is_cached`; `UNIQUE(run_id, bad_case_id)` makes re-prepared runs idempotent. Cluster membership is still derived from `probe_cluster_probes`, so there is no extra candidate-to-cluster table.
- Migration `0020` follows `0019`; SQLite uses batch mode and MySQL uses ALTER. Columns, indexes, and foreign keys are guarded by presence checks, so repeated upgrades and retries after a partially applied DDL only add what is missing. When `bad_case_analysis`/`probe_reports` are absent the matching evolution is skipped; when `bad_cases` is absent the candidate table is still created without that foreign key. Backfills only touch NULL or default values: workspace comes from the linked case, conclusion maps the newest `analysis_status`, `nonissue` or blank `attribute_type` becomes NULL, cache keys are recomputed in Python because SQLite has no sha256, and orphan probes stay NULL.
- Foreign keys belong to the migration alone: the workspace/run columns on `probe_reports` and the workspace/case columns on candidates stay plain strings in the ORM tables, because `ensure_fixture_external_tables` bootstraps only the problem-side metadata and a cross-metadata foreign key would break `create_all` table ordering; the migration is the schema authority.
- Compatible reads: `get_analysis` moves from `one_or_none()` to `updated_at DESC, id DESC LIMIT 1`, so a case with several rows no longer raises `MultipleResultsFound`; snapshots and batched analysis order by case, time, and id, while the V1 API still shows the newest compatibility row and full multi-attribution display waits for m11-01.

## Alternatives considered

- **A new V2 attribution table**: it would cut the `probe_id` chain used by `/api/probes/*` and `probe_cluster_probes`, and leave two id systems; rejected.
- **Tighten `probe_id`/`cache_key` to NOT NULL and delete historical rows**: production has no data, but fixtures and development databases hold V1 `unanalyzed` rows; deleting them or inventing probes rewrites history; rejected and kept as an explicit NULL exception.
- **Read `cache_key` in the application before insert/update**: concurrent writers would hit the unique key or create duplicate probes; rejected in favor of dialect-atomic upserts.
- **Persist only `included=true` candidates**: run details could not explain why a case missed the potential set or which policy excluded it; rejected in favor of storing every row.
- **Backfill cache keys with SQL `SHA2` or a custom function**: SQLite has no built-in `sha256`, so both dialects cannot share it; rejected in favor of a Python loop inside the migration.
- **Declare every foreign key on the ORM tables**: cross-metadata foreign keys break `create_all` during external-table bootstrap; rejected, foreign keys stay in the migration.
- **A separate candidate-to-cluster table**: a candidate is a run-level fact and cluster membership is its subset, so a second table would drift; rejected, see design 06 §5.10.

## Consequences

- Several attributions per case are now normal; legacy read endpoints return the newest row, and showing them all is m11-01's job.
- Concurrent upserts of one cache key converge on one `probe_id`; `reused_count` audits cache hits and does not count runs.
- Historical V1 rows keep `analysis_status`/`analysis_result`; V2 rows leave them NULL, so legacy readers degrade to an empty state.
- Orphan historical probes keep a NULL `cache_key` and can never hit the cache; the legacy probe endpoint still reads them.
- The migration is retryable and downgradeable; downgrade first trims each case to its newest row and maps V2 NULL statuses back to `analyzed_*`, so it is not a lossless replay and production rollback should prefer reverting the application while keeping the new schema.
- Candidates are deleted with their run; workspace deletion still cascades under the stored foreign keys (declared on both MySQL and SQLite at creation time).
- No API, service, or frontend change: legacy endpoints do not expose the new columns or table yet.
