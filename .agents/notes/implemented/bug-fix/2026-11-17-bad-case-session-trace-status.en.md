# Agent Note: express trace status for a bad case without a Session

Status: implemented

English | [中文](2026-11-17-bad-case-session-trace-status.md)

## Problem

The production bad-case list can read a reported row, but opening the detail returns `404 BAD_CASE_NOT_FOUND` and the frontend says the problem no longer exists or was deleted. The row was not missing: root-sync had no usable `sessionSource`, fell back to the unconfigured global query, failed with `SESSION_QUERY_UNAVAILABLE`, and never materialized the Session. The old read model folded "the case exists but its Session does not" into "the case does not exist".

The same case therefore had inconsistent read paths: overview read `bad_cases` directly, the Session list returned empty with `pendingSessions`, and detail answered 404. Operators could not distinguish syncing, sync failure, an upstream without a trace, and a real deletion, and root-sync kept walking the 1m/5m/15m/1h ladder for deterministic failures.

## Decision

Existence is authoritative on the `bad_cases` row; trace readiness is a separate derived dimension. `service/bad_cases/session_status.py` maps `bad_case_root_sync` plus Session readability to five public states: `ready/pending/syncing/failed/unavailable`. The overview list batch-reads sync state and Session presence for one page of roots, and detail first checks the case-only row for 404, then checks trace readiness.

Detail returns `404 BAD_CASE_NOT_FOUND` only when the case row is absent. When it exists but the Session is not ready, detail returns `409 BAD_CASE_SESSION_PENDING` (pending/syncing) or `503 BAD_CASE_SESSION_UNAVAILABLE` (failed/unavailable) with `syncStatus/lastError/retryable/nextRetryAt/lastAttemptAt` and case identity in `details`; the frontend renders a status panel from it. List items expose the same fields, and an unready row lands on that status panel in the error detail rather than on 404 copy.

The error-detail page does not replace the whole workspace: `ErrorSidebar` and `error-head` stay in the trace branch, and `TraceStatusPanel` replaces only the execution flow and the description/attribution tabs. Without a Session the sidebar shows the current case title, ID, object name, `syncStatus` badge, and attribution empty state or count; the header renders from the 503 `details` `createdAt/objectName`, the route `sid`, and the attribution endpoint `total`, and "Back to Session" is disabled when the Session is unreadable. The attribution count reuses `GET …/bad-cases/{id}/attributions`; no case read endpoint is added.

Deterministic failures (`SESSION_QUERY_UNAVAILABLE`, auth/version incompatibility, a source/Session mismatch, traversal limits, unsupported runtime, empty trace, and similar) report `retryable=false` and leave the scheduler's candidate set to avoid meaningless backoff; with no usable source at all, every unready state reports `retryable=false`. A re-report that carries a `sessionSource` gives a parked deterministic failure one fresh claim, and a startup with a usable source resets both those rows and synced roots whose Session disappeared to pending, as the re-trigger entry after a configuration change. The real 404 semantics and the existing happy path are unchanged.

## Alternatives considered

- Persist a new `unavailable/blocked` status with a migration: it would express the block directly, but this issue needs no new data and would widen the state machine and backfill surface. Derive it from existing fields first, and revisit persistence once the platform's `traceAvailable/noTrace` signal is a stable contract.
- Keep the 404 for detail and attach a `reason`: the smallest change, but it keeps presenting "not ready" as "missing", so browsers and third-party callers still misread data loss.
- Query `bad_case_root_sync` per list row: straightforward but N+1; batch-reading root state and Session presence per page fits the overview read path.
- Keep automatic retries for deterministic failures: configuration fixes would recover without a restart, but meaningless jobs and noisy logs would continue. Startup re-arming plus the manual sync entry is the chosen trade-off.
- Add a case-only read endpoint for the status page: it would add fields such as object type to the sidebar, but title, object, report time, state, and attribution count already come from the 503 `details` and the attribution endpoint. A new endpoint would widen the contract; leave it for the real need of listing sibling cases from the same root without a Session.

## Consequences

- The API gains two stable codes; OpenAPI, generated TypeScript types, and the error matrix move together. Old clients may still treat 404 as missing, but must handle 409/503 to see the state.
- The list adds two batch queries (sync state, Session presence) independent of page size; detail adds one case-only query.
- Deterministic failures are not fully consistent across views: `acquisition.status` still counts them under `failed` because the durable status remains `failed`; a restart with a usable source briefly reports pending until the next sync result.
- Existing rows without a Session need no backfill; the next read derives their state.
- The unready detail no longer degrades into a single-column status page: the two-column shell matches the prototype at 1440px, narrow screens keep stacking through the existing media query, and the sidebar presents only the current case rather than inventing sibling rows.
