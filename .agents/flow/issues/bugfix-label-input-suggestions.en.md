# Autocomplete workspace label input from existing catalog labels

English | [中文](bugfix-label-input-suggestions.md)

```yaml flow
kind: issue
id: bugfix-68
milestone: bugfix
depends:
  - bugfix-60
priority: P2
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - docs/**
  - .agents/**
adr: []
github:
  number: 629
  url: https://github.com/Shadow-Azure/harness-evolution/issues/629
```

## Background

The workspace "Badcase types" tab currently offers a bare text input, so a space administrator must remember exact label names from the public catalog. Labels match exactly and case-sensitively, so one wrong character silently disables a rule, and a fresh environment gives no hint about which labels the public repository actually contains. The data plane already keeps the `bad_cases.catalog_label` projection column (#582), which can serve as the suggestion source.

## Goals

Provide a suggestion dropdown backed by the current `bad_cases.catalog_label` values: prefix filtering while typing, the most frequent public labels on focus, and one-click insertion into the pending draft. Free-text entry stays available for labels that are not synced to this installation yet.

## Design authority

- [17 · Public badcase label routing §6 API / §7 workspace admin UI](../../../plans/fullstack-design/17-workspace-bad-case-label-routing.md)
- [05 API design](../../../plans/fullstack-design/05-api-design.md): workspace-prefixed endpoints and the viewer/member read boundary
- [17 §2.3]: `catalog_label` is a query projection of `meta_data.label`, not a second source of truth; suggestions read that column only.

## Problem, investigation and root cause

1. The input has no suggestions: `BadCaseLabelsTab.vue` renders only an `input` plus an "Add" button.
2. The data plane already supports it: `bad_cases.catalog_label` is a nullable projection written at sync time, and `ix_bad_cases_catalog_label` already exists; `SELECT DISTINCT` and `LIKE 'prefix%'` both use it consistently on SQLite and MySQL.
3. The frontend cannot reach the vocabulary: `GET /api/workspaces/{wid}/bad-case-labels` returns only the workspace's configured rules and its count, and the contracts package has no type for suggestions.
4. Collecting candidates client-side is wrong: fetching all bad cases just to read labels is heavy and cross-workspace, while reusing another workspace's rule set would leak who subscribes to what.

Root cause: a missing read-only label vocabulary endpoint, plus an input control without remote completion.

## Implementation

The only recommended approach: add one read-only suggestion endpoint and swap the input for a remote autocomplete control. Saving semantics (full-set replacement) stay unchanged.

- **API**: `GET /api/workspaces/{wid}/bad-case-labels/suggestions?q=<prefix>&limit=<n>`, guarded by `require_workspace_role("viewer")`, returning `{ "items": [ { "label": "review", "badCaseCount": 12 } ] }`.
  - Source: `SELECT catalog_label, COUNT(*) FROM bad_cases WHERE catalog_label IS NOT NULL [AND catalog_label LIKE :escaped_prefix || '%'] GROUP BY catalog_label ORDER BY count DESC, label ASC LIMIT :limit`.
  - Parameters: optional `q` up to 128 characters; `limit` 1–50, default 20; `%` and `_` escaped as literals (the same escaping the session search uses). An empty `q` returns the most frequent labels.
  - Why a workspace prefix: it reuses the existing viewer authorization and 404 semantics. The vocabulary is the public catalog's, so it is not narrowed by current-space visibility (a space with no rules sees no cases yet) and never reads another workspace's rules.
- **Frontend**: replace the plain input in `BadCaseLabelsTab.vue` with `el-autocomplete` (already registered in `test/setup`):
  - remote `fetch-suggestions` with a 200 ms debounce, `value-key="label"`, rendering `label · N cases`;
  - free-text entry stays (a new label may not be synced yet); do not rely on `select-when-unmatched` side effects;
  - configured or duplicate labels are filtered out of the list; selecting only adds to the draft (never saves), and the "Add" button plus Enter keep working;
  - when the suggestion endpoint fails, degrade to plain typing without blocking save; loading must not clear typed text.
- **Contracts**: add `WorkspaceBadCaseLabelSuggestion` and `WorkspaceBadCaseLabelSuggestionListResponse`, then run `pnpm contract:generate` so `packages/contracts` carries them.
- **Docs**: extend design 17 §6 with the endpoint and §7 with the dropdown interaction; update the Agent Note `2026-11-24-workspace-bad-case-label-routing` API/UI paragraph and re-record the pair.

## Implementation steps

1. Write the failing tests first: API cases for DISTINCT, prefix filtering, `limit` bounds, empty `q` ordering by count, `NULL` exclusion, viewer readable, 401 unauthenticated, 422 invalid `limit`; component cases for suggestion rendering, selection into the draft, free text, configured-label filtering, and endpoint-failure degradation.
2. Implement the repository query (reusing the `bad_cases` index), the service, the route, and the Pydantic response model.
3. Run `pnpm contract:generate`; add the frontend API call plus a composable under the `adminBadCaseLabels` prefix for invalidation.
4. Swap the input for `el-autocomplete` with debounce, filtering, and degradation; extend the component tests.
5. Mirror the dropdown in the prototype `plans/ui-prototype-v2/harness-evolution.html`, and update design 17 plus the Agent Note.

## Dependencies and boundary

- Depends on: `bugfix-60` (#582) for the `catalog_label` projection and label configuration chain; this issue never changes the save/reconciliation transaction.
- Delivery boundary: read-only suggestions plus the input control; no change to label matching, sync, or a label dictionary table.
- Non-goals: no label management/rename/delete backend; no fuzzy full-text search (prefix only); no cross-workspace case counts per label.

## Verification

```sh
cd apps/api && .venv\Scripts\python.exe -m pytest tests/workspaces/test_bad_case_labels_api.py -q
pnpm --filter @harness/web exec vitest run src/pages/workspaces/components/BadCaseLabelsTab.test.ts
pnpm contract:check && pnpm typecheck && pnpm lint:api && pnpm lint:web
```

- With three `catalog_label` values (`review` twice, `tool-use` once, plus a `NULL`), `GET .../suggestions` returns `[review(2), tool-use(1)]`; `?q=rev` returns only `review`; `?limit=1` returns only `review`; unauthenticated returns 401.
- UI: focusing the input shows suggestions; typing a prefix filters them; selecting adds a chip without persisting (the save button lights up); typing a label absent from the catalog still adds; after saving, counts recompute from the full replacement set.

## Acceptance

- The suggestion endpoint returns only non-null `catalog_label` values, ordered by frequency then label, honoring prefix and `limit`, readable by viewers and rejected when unauthenticated.
- The input shows a suggestion dropdown without blocking free text; selection never auto-saves; configured labels are absent from suggestions.
- A failing suggestion endpoint still allows manual add and save.
- Save-time reconciliation, counters, and workspace isolation stay identical to the current behavior.

## Gates and CI

- `pnpm contract:generate` / `contract:check`, `pnpm typecheck`, `pnpm typecheck:web`, `pnpm lint:api`, `pnpm lint:web`, `pnpm test:api` (new cases), `pnpm test:web`.
- Docs: `pnpm record:i18n` for any re-recorded pair, `pnpm lint:docs`, `pnpm verify:flow`.
- CI runs the new cases and keeps coverage at or above 80%.

## Non-goals

- No label dictionary or management page, and no inference or completion of missing labels.
- No change to exact label matching; suggestions are hints, not constraints.
- No visibility into other workspaces' label subscriptions.
