# Handle null bad-case type and over-long titles in upstream bad-case sync

English | [中文](bugfix-bad-case-sync-type-title.md)

```yaml flow
kind: issue
id: bugfix-62
milestone: bugfix
depends:
  - m6-16
  - m6-17
priority: P2
status: done
scope:
  - .agents/flow/issues/bugfix-bad-case-sync-type-title*
  - .agents/flow/issues/bugfix-edit-insert-anchor-multiline*
  - .agents/notes/**
  - apps/api/app/service/acquisition/bad_case_catalog_sync.py
  - apps/api/app/third_party_api/bad_case_query/models.py
  - apps/api/tests/m6-16-bad-case-catalog-sync/**
  - plans/fullstack-design/12-bad-case-catalog-sync.md
  - plans/2026-11-25-pr606-review.md
adr: []
github:
  number: 600
  url: https://github.com/Shadow-Azure/harness-evolution/issues/600
```

## Background

### Problem

The catalog sync `bad_case_catalog_sync` reads upstream `bad_cases` page by page and writes them to the local table only after strict validation of the whole `BadCasePage`. Upstream data now contains rows with a null `bad_case_type` and over-long `title` values: the former violates the required-string constraint on `BadCaseItem.bad_case_type`; the latter has no 200-character truncation anywhere in the sync path (both the transport model and the `bad_cases.title` column are 255). A single such item makes the whole page fail `model_validate`; `HttpBadCaseCatalogSource` maps that to `BAD_CASE_QUERY_INVALID_RESPONSE` (502), and `BadCaseCatalogSyncService.run` rolls back the page, keeps the cursor, and calls `mark_failed`. The next scheduled run retries the same page from the same cursor, so one dirty row becomes a poison pill and every later bad case stays unsynced.

- Symptom one: a null `bad_case_type` rejects the whole page; the requirement is to store `self` instead.
- Symptom two: a `title` longer than 200 characters should be truncated to 200; today 201–255 characters are stored without truncation, and only values above 255 fail the page.
- Impact: the cursor stops before the bad page, the synced count stops growing, and the sync popover shows only the stable `BAD_CASE_QUERY_INVALID_RESPONSE` with no case or field to locate.

### Analysis

The call chain, data contract, live probe, and failure semantics were checked in that order; the evidence follows.

1. Call chain: `BadCaseCatalogSyncService.run` calls `BaseBadCaseSyncSource.fetch_bad_case_page`, then `HttpBadCaseCatalogSource.fetch_page` → `_parse` → `BadCasePage.model_validate`; every `ValidationError` is collapsed into `BAD_CASE_QUERY_INVALID_RESPONSE` inside `_parse` in `http.py`.
2. Data contract: `models.py:18` requires a non-null `bad_case_type` (`min_length=1`) and `models.py:24` caps `title` at 255; `domain.py:306` declares `bad_case_type` as `VARCHAR(16) NOT NULL` and `domain.py:312` declares `title` as `VARCHAR(255) NOT NULL`; migration `0010_bad_case_title.py` creates only the 255 column, and no 200 constraint exists in the codebase.
3. Live probe: `apps/api/.venv/bin/python` constructed `BadCasePage` directly (a temporary script, not committed), then the same payload went through `HttpBadCaseCatalogSource._parse`.
4. Failure semantics: `run` in `bad_case_catalog_sync.py` advances the cursor only after `commit_page` succeeds; the exception branch calls `mark_failed` and re-raises. `test_page_failure_rolls_back_and_marks_failed` in `test_catalog_sync_service.py` asserts that a failed page writes no rows and leaves the cursor at the previous page, which means the same bad page is retried indefinitely.
5. History: m6-17 (#179) already added null fallbacks for `object_name` / `object_type` and explicitly excluded `bad_case_type` / `title` in its non-goals; overview aggregates only count `bad_case_type IN ('self', 'discovery')` (`crud/overview.py:119`), so normalizing null to `self` keeps these cases visible instead of silently excluding them.

The probe output follows; the last two lines are the same payloads through `_parse`.

```text
bad_case_type=null     -> ValidationError type=string_type loc=('items', 0, 'bad_case_type')
title=201              -> page OK, item.title len=201
title=255              -> page OK, item.title len=255
title=256              -> ValidationError type=string_too_long loc=('items', 0, 'bad_case_title')
title=300              -> ValidationError type=string_too_long loc=('items', 0, 'bad_case_title')
bad_case_type=null     -> AppError code=BAD_CASE_QUERY_INVALID_RESPONSE
title=256              -> AppError code=BAD_CASE_QUERY_INVALID_RESPONSE
```

The defect is therefore not unrecoverable upstream data but a missing normalization step for these two fields; the requested 200-character rule does not exist in code at all, and the measured threshold is 255.

### Root cause

The root cause is a missing normalization layer between the transport contract and the write mapping, combined with all-or-nothing page validation.

- Contract mismatch: `BadCaseItem` assumes upstream data already satisfies the local NOT NULL and length constraints (`bad_case_type` non-null, `title` at most 255), while upstream allows null and longer text.
- No normalization: `_row` assigns `item.bad_case_type` and `item.title` directly, with no default or truncation, so these two upstream shapes can only end as a failed page.
- Amplified failure: `BadCasePage.model_validate` is atomic per page, and the service advances the cursor only after the whole page succeeds in `commit_page`; one bad row blocks the page, the next run retries the same cursor, and the impact grows from one row to every later row.
- Historical gap: the m6-17 fallback covered only `object_name` / `object_type`, and `bad_case_type` / `title` were explicitly out of scope.

### Conclusion

- Both rules are write-side sync policy: a null (or missing) `bad_case_type` stores `self`, and a `title` longer than 200 characters is truncated to 200.
- The transport model must accept the real upstream shapes (nullable type, over-long title), otherwise the normalization code never runs; every structural check in `BadCasePage` (ordering, uniqueness, limit/total, echo) stays unchanged.
- Normalization belongs only in the `_row` write mapping; the table shape, read paths, report endpoint, and existing rows stay unchanged.
- The current effective 255 limit conflicts with the requested 200 rule and should be tightened to 200; 200 is also the attribution-side short-headline budget (`attribution.py:436` and `attribution_executor.py:118` both use `[:200]`).

## Goals

- A null or missing upstream `bad_case_type` syncs successfully and stores `self`.
- A `title` longer than 200 characters syncs successfully and stores only the first 200 characters; shorter values are preserved.
- Only these two transport checks are relaxed; `BadCasePage` structure checks, other required fields, and page-level rollback semantics stay unchanged.
- Client and service tests cover the rules, and the design doc plus an Agent Note record the decision and its trade-off.

### Recommended solution

Make the smallest change in `BadCaseItem` and `_row`, keeping the m6-17 layering of "relax transport, normalize on write"; do not change the table, read paths, or page transaction.

1. `BadCaseItem`: make `bad_case_type` `str | None` (keeping the 1–16 length bound) and drop the 255 cap on `title` (keeping `min_length=1`); `extra="forbid"`, timezone validation, and every `BadCasePage` structure check stay as they are.
2. `_row`: set `bad_case_type=item.bad_case_type or "self"` and `title=item.title[:200]`; the other field mappings and fallbacks stay unchanged.
3. Tests: the client parses a null type and a 201/300-character title; the service asserts null type stores `self`, 200 characters pass through, 201/300 truncate to the first 200, and an explicit `discovery` is not overwritten; add a regression that other invalid fields still reject the page.
4. Observability: emit one structured info log when normalization happens (`badCaseId` and the affected field) without adding a state column, so upstream drift and local logic errors can be told apart.
5. Docs: record both rules in 12 §3.2/§3.3 and add an Agent Note explaining why the rule lives in the write mapping, why title truncation is lossy, and why the column stays at 255.

## Design authority

- [12 §3.2 field mapping](../../../plans/fullstack-design/12-bad-case-catalog-sync.md): field mapping, the `title` rename, and optional-field handling.
- [12 §3.3 validation, errors and serialization](../../../plans/fullstack-design/12-bad-case-catalog-sync.md): the boundary of the strict model and `BAD_CASE_QUERY_INVALID_RESPONSE`.
- [12 §4.3 updating existing rows](../../../plans/fullstack-design/12-bad-case-catalog-sync.md): the fields written by upsert.
- [06 §4.1 bad_cases](../../../plans/fullstack-design/06-database-design.md): NOT NULL and column widths for `bad_case_type` / `title`.
- Chapter 12 and 06 §4.1 win on conflict.

## Implementation

- `models.py`: relax the transport checks for `bad_case_type` and `title` while keeping every other field constraint.
- `bad_case_catalog_sync.py`: normalize type and title in `_row` and log the normalization.
- `test_bad_case_query_client.py` / `test_catalog_sync_service.py`: cover null, 200, 201, 300, explicit values, and rejection of other invalid fields.
- `plans/fullstack-design/12-bad-case-catalog-sync.md` and an Agent Note: record the rules and the trade-off.

## Implementation steps

1. Write the failing tests first: the client accepts a null type and a 300-character title; the service asserts `self` and the first-200 truncation.
2. Relax `BadCaseItem`, normalize in `_row`, and run the focused tests.
3. Add the log assertion and the "other invalid fields still reject" regression.
4. Update chapter 12 and the Agent Note, then run the doc and flow gates.

## Dependencies and boundary

- Depends on m6-16 (the catalog sync itself) and m6-17 (the existing field fallbacks).
- Non-goals: no schema change or migration, no backfill of existing rows, no change to page atomicity or cursor semantics, no skipping bad rows, no fallback for other fields, no frontend change.

## Verification

```sh
pnpm test:api -- tests/m6-16-bad-case-catalog-sync
pnpm test:db
pnpm typecheck:api
pnpm lint:api
pnpm verify:flow
pnpm lint:docs
```

- A page with a null type parses and stores `bad_case_type='self'`.
- A 200-character `title` stores unchanged; 201 and 300 characters store the first 200.
- Explicit `self` / `discovery` and short titles are not overwritten.
- Other invalid fields still yield `BAD_CASE_QUERY_INVALID_RESPONSE`, and a failed page does not advance the cursor.
- The normalization log contains `badCaseId` and the field name.

## Acceptance

- A null or missing upstream `bad_case_type` syncs successfully and stores `self`.
- A `title` longer than 200 characters syncs successfully and stores the first 200 characters.
- Values within 200 characters and non-null types pass through unchanged.
- The related tests, typecheck, lint, and flow/doc gates are green.

## Gates and CI

- `pnpm test:api` / `pnpm test:db` / `pnpm typecheck:api` / `pnpm lint:api`
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`
- `pnpm contract:check` (the client model is not part of inbound OpenAPI; no change expected)

## Non-goals

- No change to the `bad_cases` table shape, column widths, or a new migration.
- No backfill or rewrite of existing `bad_cases` rows.
- No change to page transactions, cursor advancement, or the existing "reject the whole bad page" semantics.
- No fallback for `bad_case_session_id`, a null `title`, timestamps, or other fields.
- No frontend or sync-popover change.
