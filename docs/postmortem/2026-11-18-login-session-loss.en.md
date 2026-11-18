# Production login loss: browsers dropped the refresh cookie

English | [中文](2026-11-18-login-session-loss.md)

## Impact

Every production user was affected. On the public IP over HTTP, a full reload, a new tab, an address-bar entry, and roughly 30 minutes idle all returned to the login page; in-page navigation, workspace switching, overview filters, and Session search kept working. No data was lost; the cost was repeated logins and re-authenticating every time the "bad case ID opens the error detail in a new window" path was used. Returning to the login page after explicit logout is expected and excluded from this incident.

## Timeline

All times are CST on 2026-11-18.

- 10:05 production frontend smoke started, covering overview, Session error detail, evolution, and workspace administration.
- 10:10:02 login. From 10:10 to 10:40, in-page navigation, workspace switching, overview filters/pagination, and Session filters/search all worked; `/api/acquisition/status` polled roughly every 15 seconds, 121 times in total.
- 10:40:14 that poll returned 401, the following refresh also returned 401, and at 10:40:15 the page navigated to `/login` after 30 minutes 13 seconds without user input.
- 10:45 the smoke ended. Browser cookie storage was empty, `localStorage`/`sessionStorage` were empty, and HTTPS access timed out.
- 10:59 issue #348 was created for formal tracking (it had first been filed by mistake on Shadow-Azure/ai-eval-platform#280).
- 12:10 the defect reproduced against the production build over HTTP on a non-loopback address: login succeeded but cookie storage had no `refresh_token`, and reload fell back to the login page.
- 12:12 the same script passed after the fix: reload, new tab, address bar, and idle expiry kept the session, while explicit logout still returned to the login page.

## Root cause

Direct trigger: the login response bound the refresh cookie's `Secure` flag to `settings.is_production`. Production runs over plain HTTP, and a browser drops a `Secure` cookie on an untrusted origin, so neither startup restore nor the single-flight 401 refresh had a refresh credential.

Systemic conditions:

- The cookie security attribute looked at the deployment phase rather than the browser's actual transport, while "deploy to an IP over HTTP first, add a domain and certificate later" was a normal state of the existing release flow.
- The release flow had no explicit switch for "HTTPS is not ready yet" and no production smoke assertion that the cookie actually lands in the browser.
- E2E ran on `127.0.0.1`; Chrome treats loopback as a trustworthy origin and accepts a `Secure` cookie over HTTP, so the existing tests could not expose the defect.
- The `secure` decision was repeated across login, refresh, callback, and logout instead of having one source of truth.

## Handling

- Code fix: the refresh cookie's `Secure` flag now follows the request protocol (HTTPS only), with an optional explicit `HE_COOKIE_SECURE` override; login, refresh, callback cleanup, and logout share the one decision.
- Deployment support: nginx forwards `X-Forwarded-Proto $scheme`, and the production environment template registers `HE_COOKIE_SECURE`.
- Verification: API unit tests cover HTTP production, HTTPS, the explicit switch, and an empty environment value; a production-build browser smoke over HTTP on a non-loopback address covers reload, new tab, address bar, idle expiry, and explicit logout.
- Rollout: the existing Deploy workflow ships the merge; enabling HTTPS remains a separate P0 operations action.

## Prevention

- The production template and nginx configuration pin `HE_COOKIE_SECURE` and `X-Forwarded-Proto` so Secure cannot silently degrade behind TLS termination (this PR).
- The browser smoke uses a non-loopback HTTP origin, bypassing Chrome's trustworthy-origin exception for `localhost`; screenshots and the scenario matrix ship with the PR (this PR).
- Once HTTPS is live, the same smoke must confirm the cookie carries `Secure` and regress reload, new tab, and idle expiry.
- Owner: issue #348 / flow issue `m12-14`; a future OIDC integration must reuse the same decision for its state cookie.
