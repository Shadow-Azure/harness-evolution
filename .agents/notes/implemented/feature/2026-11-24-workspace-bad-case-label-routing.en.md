# Agent Note: Associative facts and one read boundary for label-routed public bad cases

Status: implemented

English | [中文](2026-11-24-workspace-bad-case-label-routing.md)

## Problem

Production bad cases land in one public repository, and after the periodic pull the platform must route each case by `items[].meta_data.label` into every matching workspace, with lists, Sessions, statistics, and evolution all sharing one workspace boundary. The legacy `bad_cases.workspace_id` was a single column that doubled as ownership and visibility, so it cannot express "one public case belongs to several workspaces through the same label"; copying the row per workspace collides with the global `bad_case_id` primary key. Upstream `/bad-cases` has no label filter parameter, so assignment can only happen platform-side.

## Decision

- `bad_cases` keeps one canonical fact per global `bad_case_id`, while visibility moves to the `workspace_bad_cases` association keyed by `(workspace_id, bad_case_id, assignment_source)`.
- `assignment_source` has three states: `legacy_owner` (migration backfills the existing `workspace_id`), `direct_ingest` (workspace credential reporting), and `catalog_label` (public catalog label hit). The migration splits legacy rows by `bad_cases.origin`: `report` becomes `direct_ingest`, `catalog` stays `legacy_owner`, and surviving catalog rows also get their `meta_data.label` projected into `catalog_label` with `catalog_synced` set; the backfill is repeatable. One workspace and case may hold both a direct and a label association; reads deduplicate with `DISTINCT`.
- Accepted labels live in `workspace_bad_case_labels(workspace_id, label)`. A label is an exact, case-sensitive string of 1–128 characters with no surrounding whitespace, and one label may be configured by several workspaces. The PUT replacement's `items` is required; only `[]` clears all rules.
- `bad_cases.catalog_label` is a nullable projection written from a validated `meta_data.label` at sync time (direct ingest always writes `NULL`), not a second source of truth: statistics and rebuilds query the column only and never parse JSON in SQL, keeping SQLite and MySQL behavior identical and indexable.
- The catalog sync page transaction runs in order: upsert the fact → delete `legacy_owner` and stale `catalog_label` associations for the page's ids → rebuild matches with `INSERT…SELECT` → advance the cursor and assigned/unassigned/invalid counts. Any failure rolls back the whole page and never advances the cursor.
- Saving a label configuration locks the workspace in one transaction, replaces the rule set, deletes only that workspace's `catalog_label` associations, and rebuilds history from `bad_cases.catalog_label JOIN workspace_bad_case_labels`. New rules backfill history; removed rules revoke live visibility.
- Every workspace read path (Session list and tree, problem list, overview, quota, potential cases, and evolution inputs) goes through `WorkspaceReadScope.case_condition()`. `bad_cases.workspace_id` keeps only direct-ingest ownership (id conflict detection and owner display). Attribution progress matches `probe_reports.workspace_id` to the requesting workspaces instead of the case owner column, so a shared case's report counts only in the workspace that produced it.
- `GET /api/workspaces/{wid}/bad-case-labels/suggestions` is a read-only vocabulary: it aggregates non-null, non-empty `bad_cases.catalog_label` values with their case counts, takes an optional case-insensitive prefix `q` capped at 128 characters and a `limit` of 1–50 defaulting to 20, returns the top N for an empty `q`, orders by count descending then label ascending, and escapes `%`/`_` literally. Counts and ordering aggregate exact label values (SQLite's default BINARY and MySQL's `utf8mb4_bin`), so `Review` and `review` stay separate rows with their own counts. Viewers may read it; it is not narrowed by the current workspace's rules and never exposes another workspace's rule set. The workspace admin input drives a candidate dropdown from it: focus with an empty input shows the top N, typing queries by case-insensitive prefix after a 200ms debounce, already-loaded candidates are also filtered locally by a case-insensitive prefix so stale entries hide as soon as the input changes, clicking or highlighting then pressing Enter only adds the candidate to the draft, configured labels stay out of the candidates, a failed lookup silently degrades to free text, and saving still replaces the full set.

## Alternatives considered

- **Copy the public case into every matching workspace**: rejected. It collides with the global `bad_case_id` key and loses the single fact; a label change then rewrites many rows.
- **Keep `bad_cases.workspace_id`, or fall back with `workspace_id OR association`**: rejected. After catalog sync removes the `legacy_owner` row for a re-touched id, the fallback would keep showing public data in the old default workspace, breaking the visibility boundary.
- **Parse the `meta_data` JSON in SQL for the label filter**: rejected. JSON functions and indexing differ between SQLite and MySQL, and it cannot serve the missing/invalid label counting consistently.
- **Materialize a label dictionary or write back to the public repository**: rejected. No second source of truth, and no change to how upstream produces data.
- **Rewrite already-created evolution run inputs retroactively**: rejected. Persisted candidates, reports, and run snapshots never re-read live associations; a configuration change only affects later previews and new runs.

## Consequences

- Every workspace-scoped read adds one association `EXISTS`/`IN` subquery; `workspace_bad_case_labels`, `workspace_bad_cases`, and the `bad_cases.catalog_label` column are new fact surface, and the migration backfills `direct_ingest`/`legacy_owner` by `origin` plus the catalog label projection.
- `bad_cases.workspace_id` becomes a direct-ingest-only compatibility column whose removal needs its own window.
- Public catalog assignment can push a workspace's `used` above `quota`: direct ingest keeps rejecting on quota while the admin page suggests raising quota or removing a label; `used` counts distinct associations everywhere.
- A configuration save returns only after its transaction commits, so readers never observe a rule set that disagrees with its associations; sync and re-reconciliation retries stay idempotent.
- Test fixtures that write `bad_cases.workspace_id` directly must backfill the matching association per migration semantics (`report` → `direct_ingest`, everything else → `legacy_owner`), or workspace-scoped reads come back empty.
