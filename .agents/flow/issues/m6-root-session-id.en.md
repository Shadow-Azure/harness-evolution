# Show root session IDs on the error page and browser, and search sessions by them

English | [中文](m6-root-session-id.md)

```yaml flow
kind: issue
id: m6-18
milestone: m6
depends:
  - m3-01
  - m4-04
priority: P1
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
  - docs/**
adr: []
github:
  number: 181
  url: https://github.com/Shadow-Azure/harness-evolution/issues/181
```

## Background

The root session ID is the stable key shared by problem reporting, trace sync, deep links, and operations, but the UI does not treat it as first-class information: the error detail page's left sidebar shows only an unlabeled `session · <id>` line, and the right-side header metadata has no root session ID at all. The Session browser's left-side cards and right-side overview header also lack the root session ID; the cards only carry it in the DOM `data-session-id` attribute. The Session browser search box only matches title and repo (`session_families.search_text`), so a user who copies a root session ID from bad_cases, logs, or a ticket gets no result and has to scroll the list manually. While diagnosing an error, a user usually has the error page, the problem list, and the upstream system open at the same time; a root session ID that cannot be compared or copied directly increases the cost of locating the right session.

## Goals

- Make the error page's left-side session info box show a "root session ID" label and the full value instead of an unlabeled `session · id` line.
- Add the root session ID to the error page's right-side header metadata after the start time and before the repo.
- Add a "root session ID · <full ID>" line to every Session card in the browser, not only the selected one.
- Add the root session ID to the Session overview header metadata after the start time and before the repo.
- Let the Session browser search box filter by root session ID: full ID, prefix, and substring all match; matching is case-insensitive; title and repo search keep working.
- Extend only the `q` matching scope of `GET /api/sessions`; add no endpoint and no response field.
- Update the search placeholder and accessible label to mention root session ID support.
- Cover all four display locations and search with unit tests and a browser E2E scenario.

## Design authority

- [13 Root session ID display and search](../../../plans/fullstack-design/13-root-session-id.md): data source, display locations, search semantics, and boundaries.
- [03 §7 Error detail and attribution](../../../plans/fullstack-design/03-frontend-architecture.md): the information hierarchy of the error page columns.
- [07 §3.1 Session list](../../../plans/fullstack-design/07-backend-implementation.md): the `q` implementation and the boundary of `search_text`.
- [06 §3.2 session_families](../../../plans/fullstack-design/06-database-design.md): `id` is the root session key and `search_text` contains only `lower(title + repo)`.
- Chapter 13 wins if implementation and prose disagree.

## Implementation

- Backend `app/db/crud/sessions.py`: when `q` is non-empty, `list_sessions` matches either `search_text LIKE` or the root session `id LIKE`; lowercase the query and reuse `_escape_like` so `%` and `_` stay literal; ordering, `limit`, and status filters are unchanged.
- Frontend `pages/errors/components/ErrorSidebar.vue`: turn the sidebar session info box into a dedicated line labeled "root session ID" whose text and `title` use the full ID; keep the title and back entry.
- Frontend `pages/errors/Index.vue`: add the root session ID to `error-meta` after the start time in a monospace style, using the route-resolved `sessionId` and the existing wrapping rules.
- Frontend `pages/sessions/components/SessionCard.vue`: add a "root session ID · <full ID>" line below the repo/duration/tools/subagent row on every card, using `item.id`; keep the click, selection, and keyboard semantics.
- Frontend `pages/sessions/components/SessionOverview.vue`: add the root session ID to the overview metadata after the start time, using `item.id` and the same format as the error page.
- Frontend `pages/sessions/components/SearchBox.vue`: change the placeholder to "Search title, repo, or root session ID" and align the `aria-label`; keep the input behavior and 300ms debounce.
- Tests: API covers full ID, prefix, case-insensitivity, and LIKE metacharacters; Web component tests cover the error page, Session cards, and the overview; E2E covers all four displays and filtering by ID.
- Docs: add chapter 13 as the design fact; add an Agent Note explaining why the ID goes into the query condition instead of backfilling `search_text`.

## Implementation steps

1. Write failing tests: API `q=<session id>`, `q=<prefix>`, case-insensitive matching, and literal `%` / `_`; Web assertions for the error page and Session card/overview IDs; E2E for the card/overview display and filtering by ID.
2. Change the `q` condition in `SessionRepository.list_sessions` and run the focused API tests.
3. Update the error page columns, Session card, Session overview, and search placeholder, then run the Web component tests.
4. Update chapter 13, the Agent Note, and the prototype, then run the docs and flow gates.
5. Run all relevant gates and E2E to confirm no regression.

## Dependencies and boundary

- Depends on: m3-01 (Session browser search and list), m4-04 (error detail page).
- Boundary: only extend search matching and display; do not change the `SessionListItem` contract, the `search_text` write path or backfill, the error-page or Session-browser data flow, or add a copy button or endpoint.
- Non-goals are listed at the end.

## Verification

```sh
pnpm test:api -- tests/m2-06-session-query-api
pnpm test:web -- src/pages/errors/Index.test.ts src/pages/sessions/Index.test.ts
pnpm test:e2e --pattern "m3 session browser|m4 error detail"
pnpm typecheck:api
pnpm lint:api
pnpm typecheck:web
pnpm lint:web
pnpm verify:flow
pnpm lint:docs
```

- A full root session ID returns exactly that session; a prefix or middle substring returns the matching sessions.
- A query matching both an ID and a title merges results under stable ordering without duplicate cards.
- The error page renders the same root session ID in both columns, with the full value and a label.
- Every Session card and the overview render the matching session's full root session ID.
- Typing a root session ID into the search box leaves only the matching session, and the placeholder plus `aria-label` mention ID support.

## Acceptance

- Both the error page's left session box and right header metadata show a "root session ID" label and the full value.
- Every Session card and the overview header show a "root session ID" label and the full value.
- The Session browser search filters by full ID, prefix, substring, and any letter case.
- Title and repo search are unchanged; `%` and `_` remain literal.
- The relevant unit tests, E2E, type checks, and lint pass.

## Gates and CI

- `pnpm test:api`, `pnpm test:web`, `pnpm test:e2e`
- `pnpm typecheck:api`, `pnpm lint:api`, `pnpm typecheck:web`, `pnpm lint:web`
- `pnpm verify:flow`, `pnpm lint:docs`, `pnpm verify:docs`
- `pnpm contract:check` (the response contract is unchanged; no diff expected)

## Non-goals

- Do not add a separate endpoint or parameter for exact root-session-ID lookup.
- Do not write the root session ID into `search_text` or backfill existing rows.
- Do not change the error page route, data loading, problem ownership checks, or deep-link format.
- Do not add a copy button, ID highlighting, or cross-page ID navigation.
- Do not change the Session card stats, density bars, ordering, or pagination; only add a root-ID line inside the card.
