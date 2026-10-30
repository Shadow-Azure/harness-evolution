# Field fallbacks for bad-case catalog sync

English | [中文](m6-catalog-field-fallback.md)

```yaml flow
kind: issue
id: m6-17
milestone: m6
depends:
  - m6-16
priority: P1
status: in-progress
scope:
  - apps/api/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
  - docs/**
adr: []
github:
  number: 179
  url: https://github.com/Shadow-Azure/harness-evolution/issues/179
```

## Background

The catalog sync maps upstream items directly into `bad_cases`, but upstream may return null `object_name` / `object_type`. The client currently treats both as required non-empty strings, so a single null rejects the whole page with `BAD_CASE_QUERY_INVALID_RESPONSE` and stalls the entire catalog sync; the table columns are NOT NULL, so null cannot be stored directly.

## Goals

- Allow null `object_name` and `object_type` in the client while keeping every other required field strict.
- Apply storage fallbacks: when `object_name` is empty and `source` is `code_reivew` / `code_review`, use `code-review`; otherwise fall back to `source`, then to the fixed value `unknown`; `object_type` falls back to `skill`.
- Keep the fallback inside the catalog write mapping only; do not change the table shape, read paths, or existing rows.
- Cover null, empty string, missing source, and the `code-review` alias with client and service tests.

## Design authority

- [12 §3.2 field mapping](../../../plans/fullstack-design/12-bad-case-catalog-sync.md): API field to column mapping and the `title` rename.
- [12 §4.3 updating existing rows](../../../plans/fullstack-design/12-bad-case-catalog-sync.md): the fields written by upsert.
- [06 §4.1 bad_cases](../../../plans/fullstack-design/06-database-design.md): `object_name` / `object_type` are NOT NULL.
- Chapter 12 and 06 §4.1 win on conflict.

## Implementation

- `app/third_party_api/bad_case_query/models.py`: make `object_name` / `object_type` optional while keeping the length caps; `extra="forbid"` and the other required fields stay strict.
- `app/service/acquisition/bad_case_catalog_sync.py`: fallback in `_row` — an explicit `object_name` wins; when empty and `source` is `code_reivew` / `code_review`, use `code-review`; otherwise use `source`; an empty source yields `unknown`. An empty `object_type` yields `skill`; `CatalogCaseRow` keeps non-null types.
- Tests: client accepts null; service covers the source fallback, the `code-review` alias, the `unknown` fallback, and preservation of an explicit `object_name`.
- Docs: add one fallback line to 12 §3.2 and one sentence about the final value to the Agent Note decision.

## Implementation steps

1. Write failing tests: client null parsing and service source/skill/unknown mapping.
2. Relax the model and implement the `_row` fallbacks; run the focused tests.
3. Update the design and Agent Note; run doc gates.
4. Run the related suites, typecheck, and lint.

## Dependencies and boundary

- Depends on m6-16 (the catalog sync itself).
- Non-goals: no backfill of existing rows, no fallback for `title` / `bad_case_session_id`, no change to problem read APIs, no schema change.

## Verification

```sh
pnpm test:api -- tests/m6-16-bad-case-catalog-sync
pnpm test:db
pnpm typecheck:api
pnpm lint:api
pnpm verify:flow
pnpm lint:docs
```

- A null `object_name` with a source stores that source in `object_name`.
- A null `object_name` with `source` equal to `code_reivew` / `code_review` stores `code-review`.
- A null `object_type` stores `skill`.
- A missing source stores `unknown` without a 500 or a rejected page.
- Other required fields still yield `BAD_CASE_QUERY_INVALID_RESPONSE` when missing.

## Acceptance

- Upstream null `object_name` / `object_type` no longer fail the page; catalog sync continues.
- The fallback order is explicit `object_name` → `code-review` alias (`code_reivew` / `code_review` source) → `source` → `unknown`, and `object_type → skill`.
- Non-null values pass through unchanged.
- Related tests and gates are green.

## Gates and CI

- `pnpm test:api` / `pnpm test:db` / `pnpm typecheck:api` / `pnpm lint:api`
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`
- `pnpm contract:check` (the client model is not part of inbound OpenAPI; no change expected)

## Non-goals

- No backfill or rewrite of existing `bad_cases` rows.
- No fallback for `bad_case_type` / `bad_case_session_id` / `title` / timestamps.
- No frontend or popover changes.
