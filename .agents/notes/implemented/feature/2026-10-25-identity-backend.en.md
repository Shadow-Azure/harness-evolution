# Agent Note: Identity backend and one-time event tickets

Status: implemented

English | [中文](2026-10-25-identity-backend.md)

## Problem

M1 business routes need a verifiable account seam: login, refresh rotation, forced first-password change, administrator user creation, and SSE preauthorization must be automatically testable without issuing credentials through a UI, while errors must not reveal account existence or password material.

## Decision

- `users` uses one dual-dialect Alembic migration; passwords use argon2id. An initial administrator is seeded only from `HE_ADMIN_USERNAME` and `HE_ADMIN_PASSWORD` when the database is empty and must change that password.
- Access tokens are 30-minute JWTs signed with `HE_JWT_SECRET`; refresh tokens are 14-day JWTs stored in an `httpOnly`, `SameSite=Strict` cookie scoped to `/api/auth` and marked `Secure` in production.
- Central authentication middleware makes only health, login and refresh public; login is limited to 10 attempts per IP per minute. A forced-password-change account can change its password, log out, or read its current identity; the user directory requires admin. Each refresh rotates the token and atomically consumes the old `jti` through a bounded in-process index whose entries expire with the token, while a disabled account receives `403 FORBIDDEN` for login and refresh.
- Event tickets keep the issuing user, `run:{rid}` topics and replay cursor in process for 60 seconds, and bind a random id plus expiry into an opaque process-HMAC-signed value; active grants are deleted on consumption, while an expired grant still yields `TICKET_EXPIRED` from its authenticated expiry after cleanup, and invalid topics, forgery and replay yield `TICKET_INVALID`.
- The users table and CRUD live under `db/models/` and `db/crud/`, with services limited to authentication orchestration; application-managed timestamps use Asia/Shanghai and DDL has no timestamp defaults.
- OpenAPI declares the `BearerAuth` HTTP security scheme and marks only logout, password change, current identity, the user directory, and ticket issuance as bearer-authenticated.
- Password change requires a replacement different from the current secret, while global request validation errors retain only `type/loc/msg` and never reflect submitted passwords.

## Alternatives considered

- Per-route authentication dependencies: business endpoints can be missed and forced-change rules would be scattered; rejected.
- A persistent refresh-revocation table: a single-instance M1 would gain an extra migration and cleanup task, while in-process revocation satisfies rotation acceptance for now; not adopted.
- Database sessions instead of JWTs: the forced-change claim would require a database read on every request and conflict with the short-lived JWT and frontend refresh seam; rejected.

## Consequences

- Restarting the process clears refresh revocations, login-rate windows, and the event-ticket signing key. This is a known single-instance M1 boundary and must be replaced with shared storage before scaling out.
- User deactivation is verified only at the storage layer and in login/refresh behavior; no administration endpoint exists yet. The first user directory provides only create and list operations.
- Failed login uses an argon2id dummy verification to equalize unknown-user timing, but disabled accounts return `FORBIDDEN` by design and do not participate in that timing disguise.
