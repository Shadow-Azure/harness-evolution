# Agent Note: Session query API

Status: implemented

English | [中文](2026-10-25-session-query-api.md)

## Problem

Normalized sessions, Agent events, and external issue data need stable read models for browser triage and the execution-flow graph. Client-side aggregation would diverge from list statistics, ordering, anchors, and database truth.

## Decision

The read-only `sessions` module provides list, overview, and tree queries. Lists read whole-tree aggregate columns from `session_families` and group-count `bad_cases` once for the current page. Overview reuses the same contract. Trees return flat `agents[]` rows with backend-computed labels, event offsets, and problem anchors. Search and ordering run in SQL with session ids as stable tie-breakers.

## Alternatives considered

- Aggregate trees in the browser: it duplicates semantics and forces the list page to load every tree.
- Materialize issue counts on sessions: externally owned issues can change without an invalidation path.
- Restore timeline read endpoints: the timeline page was retired, and user-input anchors cover the remaining need.

## Consequences

List and overview share one Pydantic contract, while tree fields map directly to the prototype execution-flow graph. Issue counts always reflect the read-only external table at query time. Messages and content blocks remain neither stored nor exposed. Missing sessions consistently return `SESSION_NOT_FOUND`, and SQLite plus MySQL tests constrain the query semantics.
