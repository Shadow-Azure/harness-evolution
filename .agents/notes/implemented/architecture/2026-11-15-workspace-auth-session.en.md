# Agent Note: Workspace role dependency and auth/session aggregation

Status: implemented

English | [中文](2026-11-15-workspace-auth-session.md)

## Problem

A logged-in identity answers “who are you” but not “which workspace may you operate”. V1 only had the global `users.role`; m7-02 created `workspaces`, `workspace_members`, and `workspace_id` on business tables, but no read path existed. If every business endpoint queried membership on its own, the 404/403 semantics, role order, and batching would drift per endpoint. Embedding workspace roles in the JWT would delay membership changes until token expiry and leave revocation unsolved.

The frontend also needs the current user and every visible workspace in one startup call. Splitting `me` and a workspace list adds one startup request and scatters the “user and available spaces come from one session” constraint across the client.

## Decision

- `WorkspaceRepository` owns workspace reads: one workspace, one membership row, the visible list ordered by `created_at DESC, id`, and per-workspace `used`, member count, and space-admin count grouped in SQL. The list fetches 201 rows to detect truncation, and aggregates cover only the selected spaces, so query count does not grow with workspace count.
- `require_workspace_role(minimum)` is the single dependency and reads `{wid}` from the path. A global administrator only needs the workspace to exist and passes as `global_admin`; every other user reads `workspace_members` per request and is compared on `viewer < member < space_admin`. A missing workspace and an invisible workspace share `404 WORKSPACE_NOT_FOUND`; an insufficient role returns `403 WORKSPACE_FORBIDDEN`. Workspace roles never enter the token.
- `GET /api/auth/session` returns `user + workspaces + truncated` in one payload. A global administrator sees every workspace with the `global_admin` effective role; other users see only spaces with a membership row. Each item carries live `used`, `memberCount`, and `spaceAdminCount`. More than 200 visible spaces returns the first 200 and sets `truncated=true`.
- `auth/session` joins change-password, logout, and `me` as endpoints allowed during forced password change, so the client can restore the user and spaces before changing the password.
- This slice generates `SessionPayload` and `SessionWorkspace` from FastAPI OpenAPI. The remaining workspace-management types stay explicit until their endpoints land.

## Alternatives considered

- **Put workspace roles in the access token**: membership changes and revocation would wait for token expiry, violating “read per request, effective immediately”; rejected.
- **Split `me` and the workspace list into two endpoints**: an extra startup request cannot guarantee both payloads describe the same session instant; rejected.
- **Query `used` and member counts per workspace**: 200 workspaces means 400 queries; rejected.
- **Return 403 for an invisible workspace**: it reveals whether a workspace exists and enables enumeration; uniform 404 rejected the alternative.
- **Load every workspace and truncate in Python**: the aggregate cost is unbounded before truncation; bound the list query first, then aggregate.

## Consequences

- m7-05 member writes and business endpoints from m7-06 onward reuse this dependency; membership changes apply without a new login.
- Global-admin pass-through still checks workspace existence, so a mistyped `wid` cannot pass as a valid space.
- `used` is a live count only; quota blocking waits for the ingest route (§4.17).
- The 200-row truncation is part of the contract; the workspace switcher must handle `truncated=true` as a degraded state.
- Test databases still bootstrap `bad_cases` through the fixture path, so workspace tests must create external tables first.
