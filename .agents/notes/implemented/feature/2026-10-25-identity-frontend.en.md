# Agent Note: Frontend identity state and recovery

Status: implemented

English | [中文](2026-10-25-identity-frontend.md)

## Problem

Refresh credentials must remain in an httpOnly cookie while the access token must not be persisted. Route guards, HTTP 401 handling, and forced password changes can all discover an identity-state transition. Reading cookies in each path or importing stores and routers directly creates login flashes, concurrent refresh replays, circular dependencies, and stale error pages.

## Decision

- Pinia keeps only the access token and current user in memory. Startup first tries refresh plus `/me`, then waits for router readiness and mounting. Guards reuse the same startup Promise while restoration is in flight.
- `api/http.ts` reaches identity only through injected access-token, refresh, expiry, and forced-change callbacks. Only login/refresh are public endpoints that skip recovery; concurrent 401 responses share one refresh Promise, then replay each original method and body once. `AUTH_INVALID` always retains form semantics without refreshing or triggering session expiry, while protected requests that remain unauthorized after renewal clear state and return to login.
- Login and password-change return targets accept only app-relative paths. Password changes strictly run `change-password → refresh → me → redirect`, so the new token carries the updated forced-change claim.
- A typed on-demand resolver automatically imports Element Plus inputs and buttons with base and component styles. Element Plus is excluded from Vite dependency pre-bundling to prevent a first-use full reload while retaining a separate 58.47 kB vendor chunk. The top bar condenses brand text and the user summary at 1100px and 640px breakpoints. Logout calls the backend but always clears memory and the query cache.

## Alternatives considered

- Import the store or router directly in HTTP transport: fewer registrations, but creates circular coupling and prevents tests from replacing recovery; rejected.
- Persist the access token in localStorage: faster reloads, but violates the short-lived in-memory token boundary; rejected.
- Refresh independently for every concurrent 401: simpler, but rotates the refresh cookie repeatedly and strands one replay; rejected.

## Consequences

- The first protected navigation may wait for one `/api/auth/refresh`; without a valid cookie it fails quickly with `AUTH_EXPIRED` into login, and an explicit refresh failure after password change follows the same recovery boundary.
- Every protected domain request shares transport semantics; new API modules must not handle 401 or read the refresh cookie themselves.
- User administration, registration, OAuth, and remember-password remain unavailable; those capabilities require new contracts and decisions rather than extensions of this state model.
