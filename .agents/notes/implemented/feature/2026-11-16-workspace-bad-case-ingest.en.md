# Agent Note: credential boundary, transactional quota, and idempotency for workspace bad-case ingest

Status: implemented

English | [中文](2026-11-16-workspace-bad-case-ingest.md)

## Problem

m7 delivered workspaces, members, and one-time ingest credentials, but `bad_cases` still had a single write path: the legacy catalog task upserted upstream data into the default workspace with no quota rule and no caller identity. Workspace machine ingest needs a stable entry point, and three properties must hold under concurrency: quota cannot be oversold, re-reporting one `badCaseId` cannot consume quota twice, and an id cannot be stolen or overwritten by another workspace. The credential itself must be good for exactly that one thing — a leaked `whk_` token must not read sessions, change members, or write another workspace.

## Decision

- Add `POST /api/workspaces/{wid}/bad-cases`, authenticated by a workspace credential (`Authorization: Bearer whk_…`). `AuthMiddleware` skips access-token decoding for that `POST` route only, matched by the anchored pattern `^/api/workspaces/[^/]+/bad-cases$`: trailing slashes, sub-paths, and other methods stay on the JWT path, so a leaked credential answers 401 `AUTH_REQUIRED` everywhere else.
- Credential resolution lives in the route dependency and reuses `WorkspaceService.verify_credential`: missing, unknown, or revoked → 401 `CREDENTIAL_INVALID`; credential workspace different from the URL → 403 `WORKSPACE_FORBIDDEN`; URL naming no workspace → 404 `WORKSPACE_NOT_FOUND`. The credential is verified first, so an unauthenticated caller cannot enumerate workspace ids.
- The body is a closed camelCase contract (`extra="forbid"`, aliases only): `workspaceId`, snake_case, and unknown fields all answer 422. Workspace identity comes from the URL and credential only; the body never participates. `metaData` accepts a JSON object or `null` only (arrays and scalars answer 422, matching the read model), and `createdAt` must carry a timezone offset: a naive timestamp answers 422 instead of being silently read as `+08:00`.
- One transaction covers the quota decision and the write: lock the workspace row (MySQL `SELECT … FOR UPDATE`; SQLite has no row locks, so one `UPDATE … SET updated_at = updated_at` takes the database write lock), then read the existing case by primary key, then insert or update. `used` is always `COUNT(bad_cases WHERE workspace_id)`, never a column or a cache; `X-HE-Workspace-Used` and body `workspaceUsed` come from the same post-write count.
- Ownership is decided before quota: an existing case owned by another workspace → 409 `BAD_CASE_ID_CONFLICT` (no move, no overwrite, no quota charge); owned by this workspace → 200 with every upstream field replaced; only a new id reaches the quota check, and `used >= quota` → 409 `QUOTA_EXCEEDED` (`details: {quota, used}`) without touching stored data.
- A concurrent insert of the same id trips the primary key; the `IntegrityError` is followed by a **locking** re-read of the owner: MySQL REPEATABLE READ answers a plain read from the old snapshot, while a current read (`SELECT … FOR UPDATE`) sees the row the racer just committed. Same workspace degrades to an update (201 becomes 200), a different workspace escalates to a conflict. The lock order is fixed at workspace → case, so racers never hold a lock the other needs.
- After a successful write, the same transaction inserts a `pending` `bad_case_root_sync` row if absent, making a new root session immediately discoverable; `synced` (absorbing) and `failed` (backing off) rows keep their state and are never reset by a later report. Treating a missing row as pending keeps its meaning. `claim` shares that insert-if-absent semantics: when it finds no state row and its insert hits the primary key, it returns `False` and the next tick claims the now-visible `pending` row instead of failing the whole job.
- `last_used_at` is operational metadata only: throttled to one write per 60 seconds, and a failure is logged instead of turning a committed report into a 500.
- `BadCaseIngest` / `BadCaseIngestResponse` enter FastAPI OpenAPI, so `packages/contracts` is produced by `pnpm contract:generate`; `QUOTA_EXCEEDED` and `BAD_CASE_ID_CONFLICT` join the shared error-code enum.

## Alternatives considered

- **Accept `workspaceId` in the body**: rejected. Workspace identity would have two sources that cannot be arbitrated when the credential disagrees, and a leaked credential would become a cross-workspace write entry.
- **Materialize a `used` column**: rejected. Bad cases enter at any time through the ingest path, and a counter without invalidation notifications goes stale; quota is a low-frequency write path, so one indexed `COUNT(*)` is acceptable.
- **Serialize writes with an in-process `asyncio.Lock`**: rejected. It only works in one process and hides the real row-lock semantics on MySQL; SQLite takes the database write lock instead, with an explicit dialect branch confined to local and test runs.
- **One `INSERT … SELECT … WHERE (SELECT COUNT(*)) < quota` statement**: rejected. The two dialects disagree about writability of a same-table subquery, and it gives up mapping conflicts and quota to distinct error codes.
- **Mark root sync in a separate transaction**: rejected. A committed case could lack its discoverable marker; insert-if-absent inside the same transaction is simpler and rolls back as a whole.
- **Upsert the root-sync row to `pending`**: rejected. `synced` is absorbing and `failed` carries a backoff, so resetting would refetch finished roots or shorten the retry delay.
- **Let the credential reach every `/api/workspaces/**` route**: rejected. The credential maps to no user principal, so its blast radius must stay limited to writing bad cases in that workspace.
- **Tolerate a snake_case body**: rejected. With `populate_by_name` enabled, server-owned column names such as `workspace_id` become guessable submissions; closed aliases are safer.

## Consequences

- Each SQLite report briefly holds the database write lock, serializing the write path for that span; that is inherent to a single-writer dialect and acceptable locally and in tests, while production MySQL uses workspace row locks concurrently. A lock wait beyond `busy_timeout=5000` (five seconds) surfaces as a 500 rather than unbounded queueing, so bursty local writes need a retry.
- Quota adds one `COUNT(*)` per new id; `used` is never materialized, so the workspace list and `auth/session` keep the same definition and no second count exists.
- Distinguishing 403 from 404 lets a caller holding any valid credential probe whether any workspace id exists (403 when it does, 404 when it does not); unauthenticated callers still get a uniform 401. That is the designed error matrix of §4.17, not an implementation drift.
- The credential proves workspace scope only: no per-agent identity, and no per-credential rate limit or request-body size limit, so a caller can retry at will or submit a body close to the field ceilings; immediate revocation costs one credential index lookup per report.
- The root-sync state table gains explicit `pending` rows; the scheduler's "missing row means pending" branch stays, and both count as candidates.
- The legacy catalog task still inserts into the default workspace only and, on conflict, updates upstream fields without changing `workspace_id`; the ingest path guarantees it never moves a row, but it does not take over the catalog task's write boundary.
- The MySQL concurrency quota test runs only in the lane where `HE_DB_URL` points at MySQL; local SQLite covers the equivalent semantics and the serialized branch.
