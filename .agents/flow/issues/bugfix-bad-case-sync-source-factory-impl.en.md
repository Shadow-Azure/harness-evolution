# Implement the bad-case sync source factory: base class, factory, ClaudeUpstream subclass, and writer ownership

English | [中文](bugfix-bad-case-sync-source-factory-impl.md)

```yaml flow
kind: issue
id: bugfix-50
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - .agents/flow/issues/bugfix-bad-case-sync-source-factory-impl*
  - .agents/notes/**
  - .agents/flow/issues/bugfix-bad-case-sync-source-factory-design*
  - .agents/flow/issues/bugfix-claude-edit-tool-surface*
  - .agents/flow/issues/bugfix-deploy-contract-ci*
  - apps/api/app/**
  - apps/api/alembic/**
  - apps/api/tests/**
  - tests/e2e/**
  - scripts/doc-budgets.manifest.json
  - .env.example
  - docs/architecture.md
  - docs/architecture.en.md
  - docs/architecture.i18n.yaml
  - plans/fullstack-design/06-database-design.md
  - plans/fullstack-design/12-bad-case-catalog-sync.md
  - plans/fullstack-design/16-bad-case-sync-source-factory.md
adr:
  - ../../notes/implemented/architecture/2026-11-23-bad-case-sync-source-factory.md
github:
  number: 560
  url: https://github.com/Shadow-Azure/harness-evolution/issues/560
```

## Background

[Chapter 16](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md) is finalized (#548 / bugfix-42), but production code is unchanged. The global source line is still two peer HTTP clients (`HttpBadCaseCatalogSource` and `HttpSessionQuerySource`), two procedural wiring blocks in `main.py`, and an inline if/else in `BadCaseRootSyncService._sync_root` with one BFS loop per branch. There is no explicit environment switch, and catalog sync unconditionally overwrites all 13 upstream columns of an already-reported row with the same id while counting it as `updated`. The user explicitly asked for a new issue that requires implementation, not another design-only delivery.

## Goals

- Add the three-piece module `apps/api/app/third_party_api/bad_case_sync_source/`: the `BaseBadCaseSyncSource` parent, the `ClaudeUpstreamBadCaseSyncSource` subclass, and the `BadCaseSyncSourceFactory` factory. Catalog paging and session fetching both enter through parent template methods and are implemented by the subclass.
- Collapse the global switch to `HE_BAD_CASE_SYNC_PROVIDER`, read once by the factory at composition time. Unset returns `None`; an unknown value fails startup; legacy endpoint credentials without a provider log a composition-time warning.
- Make `_sync_root` a single frozen-snapshot-to-unified-fetcher mapping with one loop. The global path synthesizes a `SessionSourceEnvelope` and reuses the existing `SessionSourceFactory` projection; `_payload()` is deleted and parity tests pin the output.
- Add `bad_cases.origin ∈ {report, catalog}` with a backfill migration. Reports write `report`; catalog sync updates only `catalog` rows, skips `report` rows, and counts them as `skipped`; the cross-dialect upsert is deleted.
- Collapse the injection seam to `create_app(bad_case_sync_source=…)`; each coordinator's `available` derives solely from whether the factory produced a source.
- Update `.env.example`, `docs/architecture.md`, chapter 12 §4.3/§5.1, and the Agent Note status consistently.

## Design authority

- [16 §1 Current inventory](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s1): file-level evidence for both source lines and the wiring block.
- [16 §2 Gap analysis](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s2): gaps R1–R7.
- [16 §3 Target design](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s3): parent/subclass/factory, switch matrix, writer ownership, and skip counting.
- [16 §5 Catalog data flow](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s5) and [16 §6 Root data flow](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s6): step-by-step JSON contracts.
- [16 §7 Compatibility and risks](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s7): snapshot extension, behavior compatibility, test impact, and implementation order.
- [Agent Note](../../notes/implemented/architecture/2026-11-23-bad-case-sync-source-factory.en.md): three decisions and the rejected alternatives.

## Implementation

- **New module**: `base.py` defines `BaseBadCaseSyncSource` with the `fetch_bad_case_page` / `fetch_session` template methods plus abstract `fetch_page` / `fetch_trajectory` / `list_children` / `build_envelope` / `close` and `from_settings` hooks. `claude_upstream.py` owns both `httpx.AsyncClient`s, the Bearer headers, timeouts, retries, backoff, and `ClaudeUpstreamEnvelopeFactory`, and declares `runtime_key="claude-code"` explicitly. `factory.py` provides registration, `provider_key`, `None` when unset, and a startup failure for an unknown provider.
- **Catalog sync**: the service depends on `BaseBadCaseSyncSource | None` and calls `fetch_bad_case_page`. `CatalogSyncResult` and the job result gain `skipped`. `BadCaseCatalogSyncRepository.commit_page` reads `origin` first, then routes rows into insert / update-owned / skip buckets with an explicit `INSERT` and an `origin="catalog"`-guarded `UPDATE`; an `IntegrityError` retries through a savepoint and becomes skipped. `_upsert_statement` and the dialect branches are removed.
- **Root sync**: `SessionSourceSnapshot` gains an optional `provider` allowed only for global sources (report with a provider, or global with a template/runtime, is rejected). `_select_source` freezes the current source provider into the global snapshot. `_sync_root` traverses with a unified fetcher built from `ReportSessionFetcher` or the global source's `fetch_session`; `_payload()` and both BFS loops are deleted.
- **Composition and switch**: `Settings.bad_case_sync_provider` maps to `HE_BAD_CASE_SYNC_PROVIDER`. `create_app` calls the factory when no source is injected; both coordinators take an `available` flag. Lifespan closes the one sync source and the report fetcher client; the old `session_query_source=` / `bad_case_catalog_source=` seams are deleted.
- **Migration**: `0032_bad_case_origin` adds `origin` (default `catalog`) and backfills report when the workspace is not the default one or `session_source` is non-null; otherwise catalog. Ingest writes `origin="report"` and never changes ownership on re-report.
- **Tests and docs**: existing fixtures move to a fake of the new parent; new tests cover the factory, subclass, parity, writer ownership, and backfill; revision assertions are refreshed. `.env.example`, chapter 12, `docs/architecture.md`, and the Agent Note are updated.

## Implementation steps

1. Add the issue trio and `flow:sync` the GitHub number; move the status to `in-progress`.
2. Land the migration and writer ownership first: `origin` column, backfill, `report` ingest, three-way catalog routing, and `skipped`.
3. Land the new three-piece module and parity tests without wiring it.
4. Extend `SessionSourceSnapshot.provider` and `_select_source`, collapse `_sync_root` to one loop, and delete `_payload()`.
5. Switch composition: factory, `create_app(bad_case_sync_source=…)`, coordinator `available`, lifespan close chain, and removal of old seams.
6. Update configuration and documentation, run focused tests plus API static gates, flow/doc gates, and contract checks; commit and open the PR.

## Dependencies and boundary

- Depends on the finalized [chapter 16 design](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md) already merged to `main` (PR #550).
- Boundary: only the bad-case sync source, catalog/root sync, composition, migration, tests, `.env.example`, and related docs. No second provider, no multi-provider coexistence, no rename of the `kind="global"` data label, and no new `skippedBadCases` contract field.
- The report protocol and error codes do not change; payload parity is pinned by tests.

## Verification

```sh
pnpm test:api -- tests/m6-15-bad-case-session-sync tests/m6-16-bad-case-catalog-sync tests/m9-07-report-session-source tests/bugfix-47-bad-case-sync-source-factory
pnpm lint:api
pnpm typecheck:api
pnpm contract:check
pnpm verify:flow
pnpm lint:docs
pnpm verify:docs
```

- Focused API tests cover the factory (unset, unknown provider, duplicate registration), subclass client ownership and envelope synthesis, global-versus-report `SessionInfo` parity, provider freezing and legacy snapshots, reported-row skipping with `skipped`, and `origin` backfill.
- `lint:api`, `typecheck:api`, `contract:check`, `verify:flow`, `lint:docs`, and `verify:docs` all pass.

## Acceptance

- The global line is enabled only by `HE_BAD_CASE_SYNC_PROVIDER`; unset makes the factory return `None` and both catalog and root statuses `unavailable`; an unknown value fails composition.
- Catalog paging and session fetching both call parent template methods; `main.py` no longer constructs HTTP clients, auth headers, retry parameters, or the two if blocks; a new upstream needs one subclass plus registration.
- `_sync_root` has one fetcher mapping and one traversal loop; the global path projects through `SessionSourceFactory.create("claude-code").project` and produces payloads field-for-field identical to the old `_payload()` (main `agent_meta=None`, subagent `{"parentAgentId": …}`, `runtime_key="claude-code"`).
- `bad_cases.origin` is fixed by the first writer; catalog sync never overwrites `origin="report"` rows, skip counts reach `skipped`, and the cursor advances in the same transaction.
- Legacy `{"kind":"global"}` snapshots remain valid; a provider on a report snapshot is rejected; error codes and retry semantics are unchanged.
- `.env.example`, `docs/architecture.md`, chapter 12 §4.3/§5.1, and the Agent Note match the implementation.

## Gates and CI

- `pnpm test:api -- tests/m6-15-bad-case-session-sync tests/m6-16-bad-case-catalog-sync tests/m9-07-report-session-source tests/bugfix-47-bad-case-sync-source-factory`
- `pnpm lint:api`, `pnpm typecheck:api`, `pnpm contract:check`
- `pnpm verify:flow`, `pnpm lint:docs`, `pnpm verify:docs`, `pnpm test:gates`
- Commit and PR titles carry `(#N)`; the PR description records migration, parity, and writer-ownership evidence.

## Non-goals

- No second upstream implementation and no multi-provider coexistence; the `bad_case_root_sync.source_kind="global"` label is unchanged.
- No report API, workspace credential, or error-code changes; no `skippedBadCases` on the status API.
- No traversal, lease, retry-ladder, or replay-parser changes; no refactoring of unrelated acquisition modules.
- No cleanup of historical snapshots; rollback behavior follows chapter 16 §7.1 startup re-arm.
