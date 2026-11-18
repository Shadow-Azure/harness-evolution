# Agent Note: derive refresh cookie Secure from the request protocol

Status: implemented

English | [中文](2026-11-18-refresh-cookie-transport.md)

## Problem

The production instance runs with `HE_PRODUCTION=true` over plain HTTP, yet the login response's `refresh_token` always carried `Secure`. A browser on an untrusted origin (a public IP HTTP page) drops that cookie outright, so a full reload, a new tab, an address-bar entry, and 30 minutes idle all had no refresh credential; in-page navigation worked, which rules out a frontend routing bug.

The login design was not wrong; the cookie's security attribute only looked at the deployment phase (`is_production`), never at the protocol the browser actually used. Deploying to an IP over HTTP first and adding a domain and certificate later is the real state of the existing release flow; until HTTPS lands, a fixed `Secure` disables the entire persistence mechanism.

## Decision

The refresh cookie's `Secure` follows the request protocol: true when `request.url.scheme == "https"`, false otherwise. An optional `HE_COOKIE_SECURE` explicitly overrides it, and an empty environment value counts as unset. Login, refresh, IdP callback cleanup, and logout share one decision function so no endpoint keeps consulting `is_production`. nginx forwards `X-Forwarded-Proto $scheme` so a TLS-terminating proxy still lets the backend see HTTPS, and the production environment template documents the switch. The cookie name, `Path=/api/auth`, httpOnly, SameSite=Strict, and the 14-day lifetime are unchanged.

## Alternatives considered

- **Enable HTTPS immediately (domain plus certificate)**: right long-term, but it needs a domain, DNS, and a certificate and would block fixing a login defect already on the main path. It stays a P0 operations action, decoupled from this code fix.
- **Drop Secure unconditionally**: the smallest edit, but it would silently degrade any future HTTPS deployment, trading one security gap for another; rejected.
- **Persist the access token in sessionStorage**: helps reload only, not new tabs, address-bar entry, or an expired token, and it widens what XSS can steal; rejected.
- **Remove `target=_blank` from bad-case IDs**: hides the symptom while new tabs and shareable links stay broken; with the cookie fixed, the new-window behavior stays.

## Consequences

- On HTTP production the refresh token travels in clear text; issue #348 explicitly accepts this interim risk. Once HTTPS lands, set `HE_COOKIE_SECURE` back to auto and verify Secure takes effect.
- With TLS terminated at a proxy, deployment must forward `X-Forwarded-Proto` or set `HE_COOKIE_SECURE=true`; otherwise the backend sees HTTP.
- The interactive 401 notice, polling backoff, and sessionStorage fallback remain P2 and out of scope; startup restore and single-flight refresh are unchanged.
- The new switch applies to every cookie-writing path; a future OIDC integration must reuse the same decision for its state cookie.
