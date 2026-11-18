# Agent Note: Align workspace admin and auth copy with the current contract

Status: implemented

English | [中文](2026-11-18-admin-copy-contract.md)

## Problem

The workspace admin page, the V2 prototype and the design document described the same permissions and endpoints differently. The production spaces page only said a global admin can add any user to a space, weakening the ability to make themself a space admin. The prototype "auth access" section still used `email`, `he_session` and `204 Set-Cookie`, and `design-v2.md` §3.3 repeated that stale contract. The prototype "ingest access" payload still used the `bad_cases` table's `snake_case` fields. The API already logs in with `username`, returns `accessToken`/`expiresIn` and writes a `refresh_token` cookie; ingest already uses camelCase and rejects a workspace field in the body. Copy drift makes integrators copy the wrong contract and makes design review misread the implementation as a deviation.

## Decision

- The production spaces page and the prototype both state that a global admin can add any user, including themself, and appoint them as a space admin.
- The auth example now matches the implementation: `GET /api/auth/session` returns `PublicUser` + `SessionWorkspace` + `truncated`; `POST /api/auth/login` takes `username`/`password`, returns `accessToken`/`expiresIn`/`user` and writes an HttpOnly, SameSite=Strict `refresh_token` cookie; `refresh` and `logout` are shown too.
- Remove the production page's "replace the demo account" wording. Demo accounts stay only in the prototype login demo and are explicitly marked as prototype-only.
- The prototype and `design-v2.md` ingest example now uses camelCase `BadCaseIngest` fields and keeps the note that the body rejects a workspace field with `422`.
- Add component tests and a real-browser E2E. The E2E reads the required fields from `packages/contracts/openapi.json` and checks that the page contract, prototype and design document contain them, so the copy cannot drift silently.

## Alternatives considered

- **Change only the production page**: rejected. The prototype and `design-v2.md` are the second and third sources integrators read; stale fields there still mislead.
- **Extract the copy into a shared constant**: rejected. The prototype is a standalone static HTML file and cannot import production constants; an OpenAPI-driven test is the reliable lock.
- **Keep API compatibility for the old email / snake_case examples**: rejected. The contract already moved; adding compatibility would widen the interface and hide the drift.
- **Add account selection or demo login to the admin page**: rejected. Production does not enumerate accounts; accounts come from admins or SSO mapping.

## Consequences

- Only copy and examples change across the page, prototype and `design-v2.md`; login, cookies, RBAC and ingest writes are untouched.
- The E2E reads OpenAPI required fields, so a schema change without a copy update fails directly.
- Browser screenshots provide copy evidence; the baseline is `main` before m12-13 and the screenshots are not committed to the repository.
