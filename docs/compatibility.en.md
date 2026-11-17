# Compatibility and retirement

English | [中文](compatibility.md)

Records the V1 surfaces, trigger version, and mechanical deletion conditions inside the compatibility window; rationale lives in [Agent Note](../.agents/notes/implemented/architecture/2026-11-17-v2-compatibility-retirement.en.md). Endpoints, routes, and fields are not deleted inside the window.

## Compatibility surfaces

| Surface | Current behavior | Deletion condition |
|---|---|---|
| V1 read endpoints | `GET /api/sessions*`, `GET /api/bad-cases*`, `GET /api/probes/{id}`, `GET /api/catalogs/*`, `POST /api/evolution/probes/query`, and the unprefixed `/api/evolution/*` filter by every workspace visible to the user; `/analysis` and `/sessions/{sid}/probes` return only the legacy shape | V3 starts, and no V2 page, fixture, E2E, or document calls them |
| Workspace-less routes | `/`, `/sessions/**`, `/errors`, and `/evolution/**` redirect to the remembered visible workspace; ambiguous multi-workspace links open the chooser | V3 starts, and bookmarks, external links, and E2E no longer produce paths without `wid` |
| V1 run schema | Six-step progress for `attribution_engine='legacy-probe-import'` maps to the seven-step DTO at read time; new runs write only seven steps | No legacy run needs reading, and six-step types are gone from the contract and pages |
| Nullable compatibility columns | `bad_case_analysis.probe_id` and `probe_reports.cache_key` stay nullable for V1 rows without a probe | Existing rows are backfilled and a migration can safely tighten NOT NULL |
| Inline attribution | `BadCase.analysis` is still returned on `BadCase` and read by list cards; V2 error detail uses attribution pages/details | List cards no longer read the field and contract consumers are gone |
| Compatibility deep links | Error details accept `?obj=<name>` (prototype compatibility); `?issue=` and `?report=` were never supported | Known old links expire, and the `obj` branch, contract, and tests are removed together |
| Legacy catalog sync | `HE_BAD_CASE_CATALOG_SYNC_ENABLED=false` by default; when enabled it only upserts the default workspace by primary key and never becomes the V2 write path | V3 starts and the default workspace no longer needs historical import |

## Trigger version

The next major version is V3, the first major after V2; the compatibility window covers at least one released V2 version. No compatibility surface is deleted before V3 starts, and no new feature depends on compatibility behavior.

## Mechanical checklist

1. Search for leftovers: `rg -n "api/sessions|api/bad-cases|api/probes|probes/query|legacy-probe-import|\\bobj=" apps packages tests fixtures docs`.
2. Frontend: remove legacy API helpers, `/analysis`/`/probes` reads, and legacy route redirects; update tests and keep the regression that V2 calls only `/workspaces/:wid`.
3. Backend and contract: remove V1 endpoints, the six-step adaptation branch, and legacy types; run `pnpm contract:generate && pnpm contract:check`.
4. Database: backfill `probe_id`/`cache_key`, then tighten NOT NULL in a migration; run `pnpm test:db && pnpm test:db:mysql`.
5. Data: confirm no new legacy runs; snapshot or archive existing runs before deleting the adapter.
6. Tests and fixtures: delete legacy cases and add "old path is 404/unregistered" assertions; run `pnpm test:api && pnpm test:e2e`.
7. Documentation: update this page, architecture, and the owning Note; run `pnpm verify:docs && pnpm verify:flow`.
8. Release: confirm bookmarks, external ingest, and client docs no longer use workspace-less paths, then remove the redirects.

## Verification

- The commands above are green, and `rg` only hits this page and historical Note/plans.
- V2 pages, fixtures, and E2E call only workspace-prefixed endpoints.
- The deletion PR carries tests that old paths are unreachable and a rollback note; otherwise compatibility stays.
