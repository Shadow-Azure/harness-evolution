# Agent Note: Workspace administration, members, and ingest credentials API

Status: implemented

English | [中文](2026-11-15-workspace-admin-api.md)

## Problem

m7-03 gave every business request a workspace gate and an `auth/session` aggregate, but workspaces themselves still came only from the migration seed: there was no entry point for creating one, changing its quota, or appointing administrators, and no lifecycle for members or ingest credentials. Splitting member rules across routes would duplicate the three boundaries "space admins grant only member/viewer", "space admins cannot edit space_admin rows", and "the last space admin cannot be removed"; a credential plaintext leaking into a list response or the database would expose far more than one endpoint.

## Decision

- `WorkspaceService` owns the administration rules; routes only authorize and translate DTOs. Creating a workspace requires at least one existing initial space admin. `PUT` exposes only `quota` to space admins, answers `403 WORKSPACE_FORBIDDEN` for `name/mark`, and returns `422 QUOTA_INVALID` with `{quota, used}` when the new quota is below live usage.
- Member mutations require `space_admin` or higher. A space admin granting `space_admin` gets `403`; editing or removing an existing `space_admin` row, or removing/demoting the last space admin, gets `409 ROLE_LOCKED`. A global admin may appoint or revoke space admins but cannot leave a workspace without one. Only the global admin can appoint itself, and that writes a real membership row.
- Candidate search runs server-side against username or display name, excludes existing members, and caps `limit ≤ 20`. An empty query returns an empty page rather than the global user directory.
- Credentials use `whk_` plus 32 random bytes. The database stores only the SHA-256 hex digest and a 12-character prefix; the plaintext appears once in the create response, and lists return only `id/prefix/createdAt/lastUsedAt/revokedAt`. Each workspace holds at most three active credentials; revocation sets `revoked_at` idempotently and the hash lookup stops matching.
- `POST /api/workspaces` remains global-admin only, but the middleware uses an exact-path rule rather than a prefix rule; otherwise member and credential POSTs under the same prefix would also become admin-only.

## Alternatives considered

- **Push member rules into each route**: every endpoint would repeat role checks and 404/403 semantics; centralizing them in the service lets one permission matrix cover all routes.
- **Let space admins rename or re-describe a workspace**: the design only grants them quota; allowing it would let the workspace identity and audit ownership drift.
- **Store or echo credential plaintext**: it simplifies rotation, but one database or response leak yields a long-lived ingest credential.
- **Load the global user table in the browser for candidate search**: that exposes the global directory to space admins; the server-side search excludes members instead.
- **Use a prefix rule for `POST /api/workspaces`**: it would also make member, credential, and self-appointment POSTs global-admin only; an exact match avoids that.

## Consequences

- m7-06 and m7-07 reuse `require_workspace_role` directly; membership changes take effect on the next request.
- `verify_credential` resolves credentials by hash and revocation state, so the m8-01 ingest endpoint consumes it instead of parsing tokens again.
- Workspace creation, member changes, and credential creation add read-then-write steps; the "last admin" and "three active credentials" checks retain a narrow concurrency window. Stronger guarantees would lock the workspace row in the transaction.
- The 60-second `last_used_at` throttle belongs to the ingest path; this slice keeps the column only.
