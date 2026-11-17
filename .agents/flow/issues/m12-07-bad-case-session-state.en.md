# Handle bad cases without a Session: distinguish syncing, no-trace, and not-found

English | [中文](m12-07-bad-case-session-state.md)

```yaml flow
kind: issue
id: m12-07
milestone: m12
depends: []
priority: P1
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - docs/**
  - .agents/notes/**
  - .agents/flow/**
adr: []
github:
  number: 324
  url: https://github.com/Shadow-Azure/harness-evolution/issues/324
```

## Background

A bad case uploaded in production (`swe-2bb86…`, `[SWE-bench] astropy__astropy-12907 · not_scored`) appears in the HE bad-case list, but opening it returns `404 BAD_CASE_NOT_FOUND` and the page says the problem no longer exists. The case was not deleted: its Session was never materialized because the upload carried no usable `sessionSource`, so root-sync fell back to the unconfigured global session query and failed with `SESSION_QUERY_UNAVAILABLE`.

The same case has four inconsistent read paths: the overview list reads `bad_cases` directly and returns the row; the session list returns `items: []` with `pendingSessions: 1`; the session detail/problem list returns `SESSION_NOT_FOUND`; the bad-case detail returns `BAD_CASE_NOT_FOUND`, which the frontend renders as "problem not found or deleted".

This is not a one-off dirty row. ai-eval-platform#266 deliberately omits `sessionSource` and falls back to the attempt id when a case has no native main trace; even with HE's global query configured, an attempt id is not a native session id and still cannot be resolved. HE has no state for "the case exists, but its trace is pending or unavailable", so the read path collapses to 404.

### Impact

- Users see a clickable bad case and then a "not found / deleted" page, which looks like data loss.
- Operators cannot distinguish syncing, sync failure, upstream no-trace, and a genuinely missing case.
- root-sync keeps retrying deterministic failures on the 1m/5m/15m/1h ladder, producing pointless jobs and noisy logs.
- A dead link disguises an upstream integration gap as "data does not exist".

### Root cause

- `ProblemRepository.case_snapshot` reads the case and then requires a session family; a missing session returns `None`, and `ProblemService.get_case` maps it to `404 BAD_CASE_NOT_FOUND`.
- The overview list `OverviewRepository.page_cases` only reads `bad_cases` and never checks the session, so list and detail disagree.
- `bad_case_root_sync` already stores `status / attempts / last_error / next_retry_at / source_kind`, but neither the list nor the detail consumes it.
- `apps/web/src/pages/errors/Index.vue` renders every 404 as "problem does not exist or has been deleted".
- The platform's trace-less fallback has no explicit `traceAvailable / noTrace` signal; HE can only infer it from "no session and no session_source", and the current inference is flattened into 404.

## Goals

- Expose a trace state on list rows and detail: syncing, failed, unavailable/no-trace, not-started, ready.
- When a case exists but its session is not ready, return a distinct stable error code and structured status instead of `BAD_CASE_NOT_FOUND`.
- Render syncing / failed / no-trace as an actionable status panel (last error, next retry, upstream status entry), not as "not found or deleted".
- Keep 404 `BAD_CASE_NOT_FOUND` for genuinely missing cases.
- Mark deterministic unsyncable roots as `retryable=false` so users are not told to wait; whether to stop retrying is decided during implementation.
- Update contracts, unit tests, cross-stack E2E, and docs.

## Design authority

- [05 §3.8 workspace bad-case ingest](../../../plans/fullstack-design/05-api-design.md#38-bad-case-上报): ingest fields and the `sessionSource` contract.
- [05 §10.5 report-bound session envelope](../../../plans/fullstack-design/05-api-design.md#105-上报绑定的会话信息-envelopem9-07): envelope and error codes.
- [11 §3.4 report-bound envelope](../../../plans/fullstack-design/11-bad-case-session-sync.md#34-上报绑定的-envelopem9-07): source selection, first-claim pinning, and retry semantics.
- [06 database design](../../../plans/fullstack-design/06-database-design.md): `bad_cases` and `bad_case_root_sync` columns.
- [docs/architecture.md](../../../docs/architecture.en.md): auth, error boundary, and problem/attribution read paths.
- [per-report session source Note](../../notes/implemented/architecture/2026-11-16-per-report-session-source.en.md): m9-07 source snapshots and failure codes.

## Implementation

- **Contracts**: add a trace-state enum and bad-case list fields (suggested: `syncStatus: "pending" | "syncing" | "failed" | "unavailable" | "ready"`, `sessionReady`, `lastError`, `retryable`); add `BAD_CASE_SESSION_PENDING` and `BAD_CASE_SESSION_UNAVAILABLE` (or `BAD_CASE_NO_TRACE`); regenerate OpenAPI and TypeScript types.
- **Repository**: add `case_visibility` (case-only read, no session requirement) and `root_sync_states` (batch read `bad_case_root_sync` by root); enrich the overview page in one batch, avoiding N+1.
- **Service**: `ProblemService.get_case` first checks whether the case exists; if it exists but `case_snapshot` is empty, map `bad_case_root_sync` to 409 (pending/syncing) or 409/503 (failed/unavailable) with `details: {syncStatus,lastError,nextRetryAt,retryable}`. Only a missing case returns 404.
- **Sync status**: expose `retryable` and a stable `lastError` from `BadCaseRootSyncService`/repository; mark deterministic failures (no `session_source` and no global query) as `retryable=false` while keeping a re-trigger path for later configuration changes.
- **Frontend**: show a state chip in the overview list; when `sessionReady` is false, open a status view (or render the status panel in the error detail) instead of the "not found" page; add 409/503 branches in `errors/Index.vue` with the state, `lastError`, and a link to `/api/acquisition/status` or a retry action.
- **Compatibility**: keep 404 `BAD_CASE_NOT_FOUND` for truly missing cases; existing session-less rows gain a state on the next read without a data backfill.
- **Tests**: API cases for pending / syncing / failed / no-trace / missing; frontend state chip and copy; E2E for ingest → list → click → status view; contract snapshots and type checks.
- **Docs**: update the API error matrix, architecture error boundary, and deployment runbook so "no trace" is not a 404.

## Prototype change

Prototype file: `plans/ui-prototype-v2/harness-evolution.html`. This issue only changes the prototype, not production code; implementation will carry the same information architecture into `apps/web`.

- The overview bad-case list gains a "trace" column: `ready` / `syncing` / `failed` / `unavailable`; when not ready, the ID is no longer an error-detail link and a "view" action opens the status panel.
- The error detail gains a no-trace status panel: it states the problem was reported and not deleted, shows `lastError`, `retryable`, the last attempt, a sync-status entry, and back/copy actions.
- No-trace cases no longer get placeholder attributions (the prototype's `attributionsFor` returns empty), avoiding a "0 attributed" header with sidebar attribution rows.
- The status deep link stays `page=session&view=errors&ws=…&sid=…&case=…&dtab=desc`, reusable by the production implementation.

**Before / after**

**Overview list (left: before, right: after)**

![overview before/after](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-07-prototype-evidence/composite-overview.png)

**Error detail (left: before, right: after)**

![detail before/after](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-07-prototype-evidence/composite-detail.png)

The before screenshots inject the same synthetic case (`BC-HC-026`, `not_scored`, `SESSION_QUERY_UNAVAILABLE`) into the original prototype; the after screenshots are the modified prototype. All four use the same 1440×913 viewport, light theme, and scroll position.

## Implementation steps

1. Define the state enum, list fields, and two error codes in contracts; regenerate OpenAPI/TS.
2. Add the case-only visibility query and batch root-sync state query with repository tests.
3. Implement the `ProblemService.get_case` state mapping and `details`, keeping 404 only for a missing case.
4. Add the overview state chip, error-detail status panel, and 409/503 copy with component tests.
5. Seed fixtures for case with/without session, pending, failed, no-trace, and missing; add API and E2E coverage.
6. Update API/architecture/runbook docs, run gates, and add an Agent Note.

## Dependencies and boundary

- Dependencies: none; this issue only changes HE read models and the frontend. It does not depend on ai-eval-platform changes or on configuring #242's global upstream.
- Platform split: an explicit `traceAvailable / noTrace` signal is a follow-up cross-repo contract. This issue first makes HE honest using existing fields (`session_source` presence and `bad_case_root_sync` state).
- Data: derive from `bad_cases`, `sessions`, and `bad_case_root_sync`; no new migration. If implementation chooses a durable `blocked` state, add a migration separately.
- Non-goals: changing the happy-path sync, attribution, probes, or problem ordering; configuring #242; redesigning the error page visual system.

## Verification

```sh
pnpm test:api -- tests/m12-07-bad-case-session-state
pnpm test:web
pnpm test:e2e -- --pattern m12-07
pnpm contract:check
pnpm typecheck
pnpm verify:flow
```

- `test:api`: five states assert HTTP status, error code, and `details`; a missing case still returns 404.
- `test:web`: list chip, detail status panel, and 404 vs 409/503 copy branches pass.
- `test:e2e`: clicking a session-less case no longer shows "problem does not exist or has been deleted".
- `contract:check`: generated OpenAPI and TypeScript types have no drift.

## Acceptance

- The overview list shows a clear state for a session-less case; clicking it shows syncing / failed / no-trace, never a 404.
- The API returns 409 (or 503) with `syncStatus/lastError/retryable` for an existing case without a session; only a truly missing case returns 404 `BAD_CASE_NOT_FOUND`.
- The frontend no longer uses the 404 copy for syncing / no-trace states; the status view exposes `lastError` and a next step.
- Deterministic failures are marked `retryable=false` and do not tell users to wait.
- New tests and docs pass CI; happy-path behavior does not regress.

## Gates and CI

- `pnpm test:api`, `pnpm test:web`, `pnpm test:e2e`, `pnpm contract:check`, `pnpm typecheck`, `pnpm lint:docs`, `pnpm verify:flow`.
- CI static lane, ≥80% unit-test coverage, and docs gates remain green; add any new E2E to the serial `test:e2e` suite.

## Non-goals

- Do not change ai-eval-platform's report payload or trace generation in this issue; a cross-repo `traceAvailable/noTrace` signal is a separate follow-up.
- Do not configure #242's `HE_SESSION_QUERY_*` or backfill historical sessions.
- Do not change bad-case attribution, probes, target matching, or problem ordering.
- Do not redesign the overall overview or error-detail information architecture; only add states and branches to the existing pages.
