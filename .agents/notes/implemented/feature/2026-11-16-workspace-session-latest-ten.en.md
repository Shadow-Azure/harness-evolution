# Agent Note: workspace session latest-ten projection, exact root-ID query, and pending count

Status: implemented

English | [中文](2026-11-16-workspace-session-latest-ten.md)

## Problem

The m7 `GET /api/workspaces/{wid}/sessions` endpoint already projected root sessions from a workspace's bad cases, but it reused the legacy list semantics: up to 100 rows by default and a fuzzy `q` that matched substrings of the title or id. The workspace session page needs to load only the ten most recent roots on open, and it needs a user who types a full root session ID and presses Enter to land on exactly that session — even when the session has fallen outside the latest ten. The page also shows two different totals: how many sessions match the current filter, and how many root sessions in the workspace have no normalized trace yet (pending sync). Fuzzy matching serves neither need: a short UUID fragment can match several rows, and a title substring turns "look up an ID" into an unpredictable result. Treating the `bad_cases` row count as the pending total double-counts one root and changes with `q`/`status`.

## Decision

- V1 `GET /api/sessions` is frozen: substring search over `search_text` and `id`, and the `limit=100` default stay. V2 `GET /api/workspaces/{wid}/sessions` changes `q` to an exact full root session ID match (`lower(id) = lower(trim(q))`) and defaults `limit` to 10. One `SessionService.list` branches on `SessionFilters.exact_query`, so both endpoints share the DTO and assembly while their search semantics never contaminate each other.
- Exact mode applies to a full id only: a partial UUID, a title fragment, or an empty `q` never degrades into fuzzy search; a non-empty but all-whitespace `q` counts as no query and returns the latest ten.
- Listing and counting share the predicate set built by `_session_conditions`: workspace projection, `q` (exact or fuzzy), and `status` are written once. `count_sessions` applies the same predicates without `limit`, so `total` is the match count ignoring pagination and cannot drift when the page size changes.
- `pendingSessions` means "distinct `bad_cases.bad_case_session_id` in this workspace whose id has no `session_families` row", implemented with a `NOT EXISTS` subquery. It is computed under the workspace scope and is independent of `q`, `status`, `sort`, and `limit`. Pending roots contribute only to the count and never enter `items`.
- The workspace projection remains `session_families.id IN (SELECT bad_case_session_id FROM bad_cases WHERE workspace_id matches scope)`; exact `q` only narrows that projection. The same id reported by another workspace, or a root owned only by another workspace, never appears.
- The default order is fixed at `started_at DESC, id ASC`: sessions sharing a timestamp still have a deterministic order, so pagination and assertions never depend on implicit row order.
- When the external `bad_cases` table is absent, the list, `total`, and `pendingSessions` all degrade to `0`/empty through the existing `_scoped_reads_available` probe and cache, so a fresh installation does not 500 the session page.
- `SessionListResponse` gains required `total` and `pendingSessions` fields; V1 returns them too (additive), but V1 search and its default `limit` stay unchanged. FastAPI OpenAPI, `packages/contracts/openapi.json`, and the generated types are synchronized by `pnpm contract:generate`.

## Alternatives considered

- **Keep fuzzy search in V2**: rejected. The requirement is "type a root session ID and press Enter"; substring matching lets a short id hit several rows and a title fragment hit unexpectedly, so neither the empty state nor the selection can be decided deterministically.
- **Fetch 100 rows on the client and slice the latest ten**: rejected. `total` and `pendingSessions` need an authoritative server definition, and client slicing still downloads every full card plus its bad-case counts, defeating pagination.
- **Select every match and count rows in Python**: rejected. That removes `limit` and makes the list linear in workspace size; one `COUNT(*)` over the same predicates is direct.
- **Count pending with `LEFT JOIN session_families … WHERE id IS NULL`**: rejected. The projection is a semi-join from bad-case roots to families; `NOT EXISTS` states "no family row" more directly and keeps multiply-joined rows out of the paged query.
- **`pendingSessions = bad_cases rows - normalized roots`**: rejected. One root can be reported several times, so the difference counts cases rather than roots; the count must be distinct over `bad_case_session_id`.
- **Let `pendingSessions` follow `q`/`status`**: rejected. Pending sync is a workspace-level operational signal; searching for an unknown id must leave it unchanged, otherwise the page badge disappears while the user searches.
- **Add a pending-count table or a materialized column**: rejected. `session_families` is written by replay and `bad_cases` by external reports, and this service receives no cross-table invalidation; the count is a low-frequency read, so a live `COUNT` is more honest and avoids a migration inside this issue.
- **Move V1 to `limit=10` or exact search too**: rejected. V1 is frozen and old callers rely on fuzzy search and the 100-row default; the new semantics belong to V2 only.

## Consequences

- One V2 list request adds two aggregate queries (`count_sessions` and `count_pending_sessions`) on top of the existing current-page bad-case counts; all three read through workspace indexes and are bounded by the workspace projection.
- `lower(id) = lower(q)` prevents the exact search from using a plain leftmost prefix of the `session_families` primary key (SQLite `=` is case-sensitive, and while MySQL's default collation is not, writing `lower` on both sides keeps the dialects consistent); the projection subquery still narrows by `bad_cases(workspace_id, bad_case_session_id)` first, and an exact id usually matches one row.
- `pendingSessions` is independent of `items`/`total`, so an empty search result can still show "N pending"; that is intentional — the badge describes the workspace, not the search result.
- The V1 response gains two fields, an additive contract change; a strict old client that rejects extra response properties would notice, but no such consumer exists in this repository.
- An all-whitespace `q` behaves like no query rather than like an exact match on whitespace; the service layer owns that single `strip`, and the tests pin the resulting latest-ten behavior.
- The external `bad_cases` probe is cached for the repository's lifetime; dropping or creating that table while the process runs requires a restart to re-probe, consistent with the existing read paths.
