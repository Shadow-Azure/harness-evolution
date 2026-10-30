# Scheduled catalog sync for bad_cases

English | [中文](m6-bad-case-catalog-sync.md)

```yaml flow
kind: issue
id: m6-16
milestone: m6
depends:
  - m2-07
  - m4-01
  - m6-15
priority: P1
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - fixtures/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
  - reports/**
  - docs/**
adr: []
github:
  number: 176
  url: https://github.com/Shadow-Azure/harness-evolution/issues/176
```

## Background

`bad_cases` is currently treated as data that already exists in the database: this service only reads it, an external system writes it, fixtures seed demo rows during development, and production relies on the upstream system writing directly into the same database. The problem list, error detail, and root-session trace sync all assume that bad_cases is already present. Once upstream switches to a standalone query API and stops writing into this database, that whole chain has no source of data. m6-15 only backfills the raw traces of the root sessions behind bad_cases; it does not ingest bad_cases itself.

Upstream provides a paginated query API: `bad_case_id` is required and returns only rows with a greater id in ascending order; `offset` defaults to 0; `limit` defaults to 20 and accepts 1–200. The response contains `total` (affected by bad_case_id, not by offset/limit), the echoed offset/limit, and `items`. Item fields map one-to-one onto `bad_cases` columns, with a single title difference: the API calls it `bad_case_title`, the table calls it `title`. Upstream bad-case ids only increase, so the largest synced id is a usable incremental cursor.

## Goals

- Add an upstream bad-case query client with strict response validation, timeouts, retries, and error mapping, called serially within one process.
- Add a sync state table (single-row cursor) recording the largest synced `bad_case_id`, the synced count, the upstream unsynced count, status, attempts, last error, and timestamps.
- Add a scheduled job (kind `bad_case_catalog_sync`) that is single-flight and serial; on startup it begins when the previous run has finished; it pages through the API by cursor, writes `bad_cases`, and advances the cursor and counts after each successful page.
- Make `bad_cases` writes idempotent upserts keyed by `bad_case_id`: insert when absent, update all upstream fields (including `title` ↔ `bad_case_title`) when present, without duplicate rows and without touching related service-owned data such as `bad_case_analysis`.
- Cold-start cursor policy: when the state table has no row, start at 0, re-pull the whole catalog on the first run, and update existing rows through the upsert path (confirmed in design §4.2).
- Extend `GET /api/acquisition/status` and the shared contract with a bad_cases catalog sync block (synced, unsynced, cursor, status, last time, last error).
- Fix the "data sync" popover order to **problem counts → problem traces → session normalization → attribution analysis**; the problem-counts section shows catalog totals/synced/unsynced and state, with no new page.
- The attribution-analysis section only reads `bad_case_analysis` to show overall progress (analyzed, pending, issue, non-issue); this feature does not implement attribution or change its state machine.
- Keep the scheduled job serial and non-concurrent; the exact skip-or-reuse policy when a run is still active is confirmed in the design document.

## Design authority

- [04 §5 data seams](../../../plans/fullstack-design/04-backend-architecture.md): read/write boundaries for external tables, raw data, and fixtures.
- [05 §4.8 raw trace ingestion](../../../plans/fullstack-design/05-api-design.md): existing acquisition endpoints, status response, and job semantics.
- [06 §4.1 bad_cases](../../../plans/fullstack-design/06-database-design.md): `bad_cases` columns, primary key, and external-write convention.
- [02 F9 trace ingestion and normalization](../../../plans/fullstack-design/02-features.md): capability boundary and demo-data rules.
- [11 Scheduled sync for bad-case root sessions](../../../plans/fullstack-design/11-bad-case-session-sync.md): existing single-flight scheduling, state table, and top-nav popover patterns.
- [12 Scheduled catalog sync for bad_cases](../../../plans/fullstack-design/12-bad-case-catalog-sync.md): the design document produced before implementation, defining cursor, paging, upsert, statistics semantics, and popover copy.
- [Prototype harness-evolution.html](../../../plans/14-15-ui-prototype/harness-evolution.html): the top-nav "data sync" popover is the frontend baseline.
- Chapter 12 and the confirmed prototype win on conflict.

## Implementation

- Config: add bad-case query base URL/token, timeout, retries, catalog sync interval, page size (1–200), and a per-run time budget; when unconfigured the status is `unavailable` and the scheduler does not trigger.
- Client: adapt the paginated API under `apps/api/app/third_party_api/bad_case_query/`; strictly parse `total/offset/limit/items`, validate each item, map `bad_case_title` → `title`; do not retry 4xx, map 401/403 to an auth error, retry 429/5xx/timeouts a bounded number of times; keep calls serial.
- Database: add a single-row `bad_case_catalog_sync` table (fixed primary key) with an alembic migration verified on SQLite and MySQL; add a primary-key upsert repository method for `bad_cases` (`ON CONFLICT DO UPDATE` / `ON DUPLICATE KEY UPDATE` per dialect).
- Service: read cursor → fetch one page → upsert all items of that page in one transaction → update cursor, counts, and timestamps → continue until no more data or the per-run budget is reached; a page failure rolls the whole page back, does not advance the cursor, and records the error plus the next retry time.
- Scheduling: reuse `JobRunner` with the new job kind and a coordinator implementing single-flight, startup recovery, and a serial periodic loop.
- API and contract: add `badCaseCatalogSync` plus a read-only `badCaseAnalysis` statistics block to `AcquisitionStatusResponse`, then regenerate OpenAPI and generated types with `pnpm contract:generate`.
- Web: reorder the `TopNav` data-sync popover to problem counts → problem traces → session normalization → attribution analysis; show catalog statistics in the problem-counts row and overall progress in the attribution-analysis row; extend `syncStatus` and add component tests.
- Attribution statistics: aggregate `analyzed_issue` / `analyzed_nonissue` by `analysis_status`, use `COUNT(bad_cases)` as the denominator for pending; read-only, no writes to the analysis table.
- Tests: mock the upstream paginated service and cover paging, insert/update upsert, title mapping, empty-page termination, cursor advancement, duplicate-trigger single-flight, failure rollback and retry, unconfigured degradation, attribution statistics, the status API, and frontend rendering.

## Implementation steps

1. Produce and confirm `plans/fullstack-design/12-bad-case-catalog-sync.md`: cold-start cursor, page size, per-run budget, failure retries, unsynced-count semantics, and popover copy.
2. Contract and config: status DTO, environment variables, OpenAPI, and generated types.
3. Database: state table and upsert repository, alembic migration, dual-database tests.
4. Client: paginated query client, strict response models, serial constraint, and error mapping.
5. Service and scheduling: sync service, job kind, single-flight, and startup recovery.
6. Web: reorder the popover into four sections, add problem-counts and attribution-analysis display and states, with component tests.
7. Tests and gates; complete a local smoke run against a mock upstream.

## Dependencies and boundary

- Depends on: m2-07 (scheduling and job infrastructure), m4-01 (external problem read models), m6-15 (popover placement and the state-table/scheduling pattern to reuse).
- Boundary: adds an automatic ingestion path for bad_cases; `bad_cases` moves from "external-write only" to "external write plus sync write, idempotent by primary key"; does not change m6-15 trace-sync semantics, the existing manual pull, or field semantics of problem read APIs. CI never calls the real upstream.

## Verification

```sh
pnpm test:api -- tests/m6-16-bad-case-catalog-sync
pnpm test:db
pnpm test:web
pnpm test:e2e -- "m6-16"
pnpm contract:check
pnpm verify:flow
pnpm lint:docs
```

- With a mock upstream returning three pages, `bad_cases` row count and content match upstream and the state cursor equals the largest id.
- Re-syncing the same batch adds no rows; after upstream edits a row, the next sync updates that row's fields.
- An empty or short page stops paging; a failed page neither advances the cursor nor leaves partial rows.
- Triggering again while a run is active creates no concurrent batch.
- Synced/unsynced counts in the status API and the popover agree with the database and upstream total.
- Attribution statistics (analyzed/pending/issue/non-issue) match manual counts over `bad_cases` and `bad_case_analysis`; rows without an analysis record count as pending.

## Acceptance

- The scheduled job runs serially at the configured cadence and the cursor only increases; after a restart it resumes from the persisted cursor.
- `bad_cases` primary-key upsert inserts new rows and updates existing ones with no duplicates across repeated syncs.
- Upstream `bad_case_title` lands in `bad_cases.title` and every other field maps one-to-one.
- Failures are retryable and visible, and never leave half a page behind.
- `GET /api/acquisition/status` returns catalog sync statistics and overall attribution progress, and the popover shows the four sections in order with backend-consistent numbers.
- With upstream unconfigured the job does not start, status shows unavailable, and existing behavior is unaffected.
- All related gates are green.

## Gates and CI

- `pnpm contract:generate` / `pnpm contract:check`
- `pnpm typecheck:api` / `pnpm test:api` / `pnpm test:db[:mysql]`
- `pnpm test` / `pnpm test:web` / `pnpm typecheck:web` / `pnpm lint:web`
- `pnpm test:e2e`
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`

## Non-goals

- Do not handle upstream deletions: no row deletes or tombstone sync.
- Do not replace m6-15 root-session trace sync or change its state table.
- Do not call the real upstream from CI; real integration runs against a local mock and smoke test.
- Do not add a business-facing problem write API; sync is the only new write path.
- Do not implement the attribution-analysis workflow or change the `bad_case_analysis` state machine; the popover only aggregates it read-only.
- Do not implement field-level diffing or change auditing; writes overwrite by primary key.
