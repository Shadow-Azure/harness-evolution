# Agent Note: Root session ID display and search

Status: implemented

English | [中文](2026-10-30-root-session-id-display.md)

## Problem

The root session ID is the stable key shared by bad_cases, trace sync, deep links, logs, and tickets, but the UI does not treat it as first-class information: the error detail page's left sidebar shows only an unlabeled `session · <id>` line and the right header meta has no ID; the Session browser cards and overview header have no ID either; the search box only matches `search_text` (`lower(title + repo)`), so pasting a full root session ID returns no session. After copying an ID from an external system, a user can neither verify it on the page nor locate the session in the list.

## Decision

Show the root session ID in four places with the same "根会话 ID · <full UUID>" copy: the error detail page's left sidebar line, the error detail page's right header meta after the start time, every Session browser card below its meta row, and the Session overview meta after the start time. Cards and the overview read `SessionListItem.id` directly; no new field or request. No copy button is added; users select and copy the text.

Extend the `GET /api/sessions?q=` match to `search_text LIKE` or `lower(id) LIKE`: lowercase the query, reuse `_escape_like` for `%`, `_`, and `\`, and support full ID, prefix, and substring. The `id` is not written into `search_text`; the table schema, indexes, normalization write path, and response contract stay unchanged.

## Alternatives considered

- Append `id` to `search_text`: this changes the normalization write path, requires backfilling existing rows, and syncs fixtures; the ID is immutable, so the duplicate storage buys nothing. Match the primary-key column at query time instead.
- Add a `rootSessionId` query parameter: the frontend would have to distinguish "ID query" from "title query" and define mutual-exclusion/composition semantics; users have one search box, so extending the existing `q` is simpler.
- Allow exact ID match only: this loses prefix and substring search and is inconsistent with the fuzzy title and repo search.
- Add `rootSessionId` to `SessionListItem`: `id` is already the root session ID, and an alias field would create a second fact.
- Add a copy button for the ID: it needs extra interaction state, a failure fallback, and E2E coverage, which exceeds the minimal display-and-search scope.

## Consequences

Search changes from one `LIKE` column to two `OR LIKE` columns, and `%...%` still cannot use an index; `session_families` is root-session grained and much smaller than the agent/event tables, so the existing `limit` pagination is acceptable. Revisit indexes or full-text search if p95 regresses. Each Session card gains one ID line, increasing card height and possibly showing the list scrollbar earlier; the line is single-line ellipsis with the full value in `title`. The error page and overview meta get longer and wrap under the existing flex rules on narrow screens. The contract, database, and deep links are unchanged.
