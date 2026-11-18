# Agent Note: Align the login page with the V2 two-column information architecture

Status: implemented

English | [中文](2026-11-18-login-v2-layout.md)

## Problem

The production login page is a single white card of roughly 420px, enough for the brand, login heading, and form only; the V2 prototype uses a roughly 920px two-column card to explain workspace isolation, object-level attribution, and the latest-10 Session behavior. The prototype's right column also shows four account buttons, but those are throwaway demo fixtures; copying them would enumerate real accounts and imply identity switching. m12-11 must align the information hierarchy and visual structure with the prototype without loosening the current authentication boundary.

## Decision

- The desktop login page uses a `min(920px, 100%)` two-column card: the left column carries the brand and three static product facts (workspace isolation, attribution into the evolution flow, and the latest-10 Session behavior), while the right column keeps the username/password form, inline error, loading state, and first-login password-change hint.
- The left column reads no user directory and renders no accounts, emails, or selectable accounts; the login page makes no account-enumeration request, and Tab order goes from the left column straight to username, password, and the login button.
- At desktop widths of 760px or less the card becomes one column, hides the three long explanations and the left-column footer, and keeps the brand, heading, and one-line capability summary; at 390px there is no horizontal overflow.
- The card background, radius, border, spacing, and breakpoints reuse `styles/tokens.css`; the new `--shadow-auth-card` only moves the prototype's large-card shadow into the token layer and introduces no second visual variable set.
- The login API, Cookie, forced password change, permissions, and route guard stay unchanged; the error remains inline with `role=alert` and `aria-live=polite`.

## Alternatives considered

- **Copy the prototype account buttons**: rejected. They enumerate real accounts and imply one-click identity switching; production accounts are created only by an administrator or seeded by env.
- **Keep the 420px single card and only change the copy**: rejected. A single card cannot carry the prototype's information hierarchy, and the issue explicitly targets two columns.
- **Turn the left-column capability copy into clickable entry points**: rejected. There is no session or workspace context before login, so the links would introduce unauthenticated routes.
- **Add a separate color or shadow variable set for the login page**: rejected. `verify:web-style` requires `tokens.css` to be the only color source, and the visual baseline should stay shared with the main app.

## Consequences

- The login page's main content widens to 920px on desktop and falls back to one column on narrow screens; the page still has no top bar, and submit and redirect behavior stay unchanged.
- `tests/e2e/m12-11-login-v2-layout.test.mjs` covers the two-column/one-column layouts, absence of account enumeration, keyboard order, and the inline error; the `m1-shell` login assertions keep reusing `.auth-card` and the brand lockup.
- The structure diagram in `plans/fullstack-design/08-frontend-implementation.md` §4.1 is now two-column; the prototype account list remains demo-only and is not a production contract.
- If SSO/OIDC is added later, the integration doc in the workspace admin page remains the single source of truth, and the login page adds no third source.
