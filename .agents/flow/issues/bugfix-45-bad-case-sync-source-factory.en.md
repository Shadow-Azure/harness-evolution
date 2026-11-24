# Implement the bad case sync-source factory: base class + factory + ClaudeUpstream subclass with writer ownership

English | [中文](bugfix-45-bad-case-sync-source-factory.md)

```yaml flow
kind: issue
id: bugfix-45
milestone: bugfix
depends: [bugfix-42]
priority: P2
status: in-progress
scope:
  - apps/api/app/**
  - apps/api/alembic/**
  - apps/api/tests/**
  - tests/e2e/**
  - .env.example
  - docs/architecture.md
  - docs/architecture.en.md
  - docs/architecture.i18n.yaml
  - scripts/doc-budgets.manifest.json
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/architecture/2026-11-23-bad-case-sync-source-factory.md
github:
  number: 560
  url: https://github.com/Shadow-Azure/harness-evolution/issues/560
```

## Background

[Chapter 16 design](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md) is final (#548 / [bugfix-42](bugfix-bad-case-sync-source-factory-design.en.md)), but the production code has not changed: the global source line is still two peer HTTP clients (`HttpBadCaseCatalogSource` and `HttpSessionQuerySource`), `main.py` still assembles them in two procedural blocks, and `BadCaseRootSyncService._sync_root` still switches with an inline if/else, each branch carrying its own BFS; `.env` has no explicit switch for the global line; and the catalog sync unconditionally overwrites 13 upstream columns of an already reported row with the same id while counting it as `updated`. The user explicitly asked for a new issue and for the implementation, and does not accept a design-document-only delivery.

## Goals

- Add three pieces under `apps/api/app/third_party_api/bad_case_sync_source/`: the base class `BaseBadCaseSyncSource`, the subclass `ClaudeUpstreamBadCaseSyncSource`, and the factory `BadCaseSyncSourceFactory`; both catalog paging and session fetching go through base-class template methods implemented by the subclass.
- Collapse the global-line switch into `HE_BAD_CASE_SYNC_PROVIDER`, read once by the factory at assembly time; unset returns `None`, an unknown value fails startup, and legacy endpoint credentials without a provider log a warning at assembly time.
- Turn `_sync_root` into one "frozen snapshot → unified fetcher" mapping and one loop; the global path synthesizes a `SessionSourceEnvelope` and reuses the existing `SessionSourceFactory` projection, `_payload()` is deleted, and parity tests lock the output unchanged.
- Add `origin ∈ {report, catalog}` to `bad_cases` (including a backfill migration); reporting writes `report`, the catalog sync only updates `catalog` rows, `report` rows are skipped and counted in `skipped`, and the cross-dialect upsert is deleted.
- Collapse the assembly seam into `create_app(bad_case_sync_source=…)`; each coordinator's `available` is decided uniformly by whether the factory product is `None`.
- Update `.env.example`, [`docs/architecture.md`](../../../docs/architecture.en.md), [chapter 12 §4.3](../../../plans/fullstack-design/12-bad-case-catalog-sync.md#43-已存在记录的更新)/[§5.1](../../../plans/fullstack-design/12-bad-case-catalog-sync.md#51-方言实现), and the Agent Note status in the same change.

## Design authority

- [16 §1 Current-state inventory](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s1): per-file evidence for the two source lines and the assembly section.
- [16 §2 Gap analysis](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s2): the seven gaps R1–R7.
- [16 §3 Target design](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s3): base class/subclass/factory, the switch matrix, writer ownership, and the skipped counter.
- [16 §5 Catalog-sync data flow](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s5) and [16 §6 Root-sync data flow](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s6): the step-by-step JSON comparison.
- [16 §7 Compatibility and risks](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s7): snapshot extension, behavioral compatibility, the test blast radius, and the rollout order.
- [Agent Note](../../notes/implemented/architecture/2026-11-23-bad-case-sync-source-factory.en.md): the three decisions and the rejected alternatives.

## Implementation

- **New module**: `base.py` defines `BaseBadCaseSyncSource` (the `fetch_bad_case_page` / `fetch_session` template methods plus the `fetch_page` / `fetch_trajectory` / `list_children` / `build_envelope` / `close` and `from_settings` abstract hooks); `claude_upstream.py` encapsulates the two `httpx.AsyncClient` instances, Bearer auth, timeouts, retries, backoff, and `ClaudeUpstreamEnvelopeFactory`, and declares `runtime_key="claude-code"` explicitly; `factory.py` provides registration, `provider_key`, `None` when unconfigured, and a startup failure for unknown providers.
- **Catalog sync**: the service dependency becomes `BaseBadCaseSyncSource | None` and calls `fetch_bad_case_page`; `CatalogSyncResult` and the job result gain `skipped`; `BadCaseCatalogSyncRepository.commit_page` queries `origin` and splits three ways, with an explicit `INSERT` plus a conditional `UPDATE` restricted to `origin="catalog"`, and a concurrent `IntegrityError` rolls back its savepoint, re-reads the real origin, and routes catalog rows to UPDATE and report rows to skipped; `_upsert_statement` and the dialect branches are deleted.
- **Root sync**: `SessionSourceSnapshot` gains an optional `provider` allowed only for global (report with a provider, or global with template/runtime, is rejected); `_select_source` freezes the current source's provider into the global snapshot; `_sync_root` runs one loop over `ReportSessionFetcher` / the global source's `fetch_session`, and `_payload()` plus the two BFS implementations are deleted.
- **Assembly and switch**: `Settings.bad_case_sync_provider` maps to `HE_BAD_CASE_SYNC_PROVIDER`; `create_app` calls the factory when nothing is injected, both coordinators accept `available`, and lifespan closes one sync source and the report fetcher client; the old `session_query_source=` / `bad_case_catalog_source=` injection seams are removed.
- **Data migration**: `0032_bad_case_origin` adds the `origin` column (default `catalog`) and backfills on the rule "non-default workspace or non-empty `session_source` → report, otherwise catalog"; reporting writes `origin="report"`, and re-reporting does not change ownership.
- **Tests and docs**: switch the existing fixtures to the new base-class fake; add factory/subclass/parity/writer-ownership/backfill tests; update the revision assertion; document the switch in `.env.example`; sync chapter 12, `docs/architecture.md`, and the Agent Note.

## Implementation steps

1. Add the issue trio, backfill the GitHub number through `flow:sync`, and move the status to `in-progress`.
2. Land the migration and writer ownership: the `origin` column, the backfill, reporting writing `report`, the three-way catalog split, and the `skipped` counter—lock data correctness first.
3. Land the three new-module pieces and the parity tests without wiring them up.
4. Extend `SessionSourceSnapshot.provider` and the `_select_source` freeze, collapse `_sync_root` into a single loop, and delete `_payload()`.
5. Switch the assembly: the factory, `create_app(bad_case_sync_source=…)`, the coordinator `available`, the lifespan close chain, and removal of the old injection seams.
6. Sync configuration and docs, run the focused tests, the API static gates, the flow/documentation gates, and contract checks, then commit and open the PR.

## Dependencies and boundary

- Dependencies: the [chapter 16 design](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md) is final and merged into `main` (PR #550).
- Delivery boundary: touch only the bad case sync source, catalog/root sync, assembly, migrations, tests, `.env.example`, and the related docs; do not introduce coexisting providers, do not change the `kind="global"` data label, and do not add a `skippedBadCases` contract field to the status API.
- The reporting-line protocol and error codes stay unchanged; payload-output consistency on the global line is locked by parity tests.

## Verification

```sh
pnpm test:api -- tests/m6-15-bad-case-session-sync tests/m6-16-bad-case-catalog-sync tests/m9-07-report-session-source tests/bugfix-45-bad-case-sync-source-factory
pnpm lint:api
pnpm typecheck:api
pnpm contract:check
pnpm verify:flow
pnpm lint:docs
pnpm verify:docs
```

- The focused API tests cover: factory unconfigured/unknown provider/duplicate registration, the subclass closing both clients and synthesizing the envelope, `SessionInfo` parity between global and report, the provider freeze and old snapshots, skipping already reported rows with `skipped`, and the `origin` backfill.
- `lint:api`, `typecheck:api`, `contract:check`, `verify:flow`, `lint:docs`, and `verify:docs` are all green.

## Acceptance

- The global line is enabled only by `HE_BAD_CASE_SYNC_PROVIDER`; when unset the factory returns `None` and both catalog and root status are `unavailable`; an unknown value fails at assembly time.
- Catalog paging and session fetching both call the base-class template methods first; `main.py` no longer hand-writes HTTP clients, auth headers, retry parameters, or the two if blocks; a new upstream needs only one subclass plus a registration.
- `_sync_root` has only one fetcher mapping and one traversal loop; the global path produces `SessionInfo` through `SessionSourceFactory.create("claude-code").project`, and the payload is field-for-field identical to the old `_payload()` (including main `agent_meta=None`, subagent `{"parentAgentId": …}`, and `runtime_key="claude-code"`).
- The first write of `bad_cases.origin` decides ownership; the catalog sync never overwrites `origin="report"` rows, the skip count lands in `skipped`, and the cursor and counters advance in the same transaction.
- Old snapshots `{"kind":"global"}` are still claimable; a new snapshot carrying `provider` is rejected on report; error codes and retry semantics are unchanged.
- `.env.example`, `docs/architecture.md`, chapter 12 §4.3/§5.1, and the Agent Note match the implementation.

## Gates and CI

- `pnpm test:api -- tests/m6-15-bad-case-session-sync tests/m6-16-bad-case-catalog-sync tests/m9-07-report-session-source tests/bugfix-45-bad-case-sync-source-factory`
- `pnpm lint:api`, `pnpm typecheck:api`, `pnpm contract:check`
- `pnpm verify:flow`, `pnpm lint:docs`, `pnpm verify:docs`, `pnpm test:gates`
- Commit and PR titles carry `(#N)`; the PR description lists the migration, parity, and writer-ownership evidence.

## Non-goals

- Do not add a second upstream implementation or support coexisting providers; do not change the `bad_case_root_sync.source_kind="global"` data label.
- Do not change the reporting API protocol, the workspace credential semantics, or the error codes; do not add `skippedBadCases` to the status API.
- Do not change the traversal/lease/retry ladder or the replay parsing chain; do not refactor unrelated acquisition modules.
- Do not clean up historical snapshots; rollback compatibility follows the startup re-arm handling in chapter 16 §7.1.
