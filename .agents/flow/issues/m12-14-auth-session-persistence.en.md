# Persist login on HTTP production: derive refresh cookie Secure from transport

English | [中文](m12-14-auth-session-persistence.md)

```yaml flow
kind: issue
id: m12-14
milestone: m12
depends:
  - m7-03
priority: P2
status: in-progress
scope:
  - apps/api/app/api/auth.py
  - apps/api/app/config.py
  - apps/api/tests/identity/**
  - deploy/**
  - docs/**
  - tests/e2e/**
  - plans/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-18-refresh-cookie-transport.md
github:
  number: 348
  url: https://github.com/Shadow-Azure/harness-evolution/issues/348
```

## Background

The production instance runs with `HE_PRODUCTION=true` over plain HTTP (public IP first, nginx listens on 80 only). `set_refresh_cookie` hard-codes `secure` to `settings.is_production`, so the login response sends a `Secure` `refresh_token` cookie; browsers drop it on an untrusted origin (a public IP HTTP page). After a full page load, a new tab, an address-bar entry, or roughly 30 minutes idle, startup or the single-flight 401 refresh has no refresh cookie and falls back to the login page; in-page navigation is unaffected, so this is not a frontend routing bug. Production evidence, timeline, and acceptance scenarios live in issue #348.

## Goals

- On HTTP production, send a refresh cookie the browser stores, so reload, new tab, address-bar entry, and idle token expiry keep the session.
- Keep sending a `Secure` cookie for HTTPS direct traffic or TLS terminated at the reverse proxy, without weakening HTTPS deployments.
- Keep explicit logout clearing the cookie and returning to the login page.
- Preserve the existing httpOnly, SameSite=Strict, Path=/api/auth, and 14-day refresh-cookie contract.

## Design authority

- [plans/fullstack-design/05-api-design.md §Auth endpoints](../../../plans/fullstack-design/05-api-design.md): the httpOnly + SameSite=Strict + 14-day refresh-cookie contract and login/refresh/logout behavior.
- [plans/fullstack-design/08-frontend-implementation.md §HTTP transport](../../../plans/fullstack-design/08-frontend-implementation.md): startup restore and single-flight 401 refresh; this change leaves that chain intact.
- [docs/architecture.en.md](../../../docs/architecture.en.md): authentication and failures share one boundary.

## Implementation

- Add an optional boolean `Settings.cookie_secure` (`HE_COOKIE_SECURE`); empty means derive from transport, and an empty environment string counts as unset.
- Route every refresh-cookie decision in `app/api/auth.py` through `refresh_cookie_secure(request)`: an explicit switch wins, otherwise only `request.url.scheme == "https"` enables Secure. Login, refresh, IdP callback cleanup, and logout share the same decision.
- Pass `X-Forwarded-Proto $scheme` from nginx so a TLS-terminated backend sees the real protocol; register `HE_COOKIE_SECURE` in the production environment template.
- Add unit tests for HTTP production, HTTPS, the explicit switch, and the empty environment value.
- Drive a production-build HTTP browser smoke covering reload, new tab, address bar, idle expiry, and logout.

## Implementation steps

1. Add the optional cookie-security switch and normalize an empty environment value.
2. Compute Secure from the request protocol in the auth HTTP adapter, replacing every fixed `is_production` decision.
3. Update the nginx proxy header and the production environment template.
4. Add API tests and run lint/typecheck/test plus the browser smoke.

## Dependencies and boundary

- Depends on: m7-03's refresh-cookie and startup-restore chain.
- Boundary: only the cookie's Secure attribute changes; cookie name, path, lifetime, SameSite, and httpOnly stay as they are.
- The bad-case new-window link is unchanged; with the cookie fixed, a new tab keeps the session naturally.
- GitHub #348 keeps the production evidence verbatim; this file is the implementation contract, so merge the body by hand before `pnpm flow:sync` to avoid overwriting screenshots and the timeline.
- The same PR merges the latest main and aligns the local status of the already-closed m12-09 / m12-13 to done, unblocking `flow-online` for every PR.

## Verification

```sh
pnpm test:api -- tests/identity/test_auth.py
pnpm lint:api
pnpm typecheck:api
```

- HTTP production login responses omit `Secure`, and `POST /api/auth/refresh` returns 200.
- HTTPS login responses include `Secure`; an explicit `HE_COOKIE_SECURE=true` includes it over HTTP too.
- A production-build browser smoke keeps the workspace after reload, new tab, address-bar entry, and idle expiry, and returns to `/login` after logout.

## Acceptance

- On HTTP production, the browser cookie store contains `refresh_token`; reload, new tab, address bar, and 30 minutes idle keep the session.
- Explicit logout still returns to `/login` and clears the refresh cookie.
- The `Secure` flag on HTTPS deployments does not regress; TLS-terminating proxies can opt in with `HE_COOKIE_SECURE`.
- Overview, Session, evolution, and workspace administration regressions introduce no new 401 loop.
- Relevant API tests, lint, typecheck, e2e, and CI pass.

## Gates and CI

- `pnpm test:api`, `pnpm lint:api`, `pnpm typecheck:api`.
- `pnpm test:e2e` and the cross-stack integration test.
- `pnpm verify:flow --diff origin/main`, `pnpm verify:docs`, `pnpm contract:check`.

## Non-goals

- No domain or certificate purchase and no HTTPS enablement inside the repository; the P0 HTTPS deployment still proceeds through the existing operations release flow.
- No P2 fallbacks: no interactive 401 notice, no polling backoff, and no access token in sessionStorage.
- No change to the bad-case ID new-window link or the detail-page information architecture.
