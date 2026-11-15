# Agent Note: Authentication-provider seam and callback placeholder

Status: implemented

English | [中文](2026-11-15-auth-provider-seam.md)

## Problem

Password verification, user lookup, and token issuance all lived in `IdentityService`. Adding Cookie or SSO would force the login path, error codes, and frontend contract to change together; without it there was no automatically verifiable callback error contract either. User administration also allowed an administrator to create another `admin`, conflicting with the single-global-admin acceptance.

## Decision

- `AuthProvider` exposes only `authenticate(Credentials) -> ProviderIdentity | None`; `PasswordProvider` keeps the existing argon2id check and dummy-hash timing equalization. `ProviderRegistry` selects an implementation from `HE_AUTH_PROVIDER` at startup. `cookie` and `oidc` are reserved values: selecting one raises `AuthProviderConfigurationError` instead of silently falling back to password.
- `SessionBridge` maps a verified identity to an existing user: password identities by internal id, external identities by the unique `(auth_provider, external_subject)` key. A failed mapping returns `403 AUTH_NO_MAPPING` and creates nothing; a disabled account returns `403 FORBIDDEN`. A mapped user receives the same access/refresh pair as password login, so business and frontend contracts stay unchanged.
- `CallbackService` implements the placeholder callback with a signed nonce and a short-lived state cookie (`HttpOnly`, `SameSite=Lax`, 10 minutes): no provider is `501 AUTH_PROVIDER_NOT_CONFIGURED`, a missing/expired/mismatched state is `400 AUTH_STATE_INVALID`, a missing code or provider rejection is `401 AUTH_INVALID`, an exchange failure is `502 AUTH_PROVIDER_ERROR`, and a failed mapping is `403`. Success redirects to `HE_WEB_BASE_URL` with the refresh cookie. The callback is public and shares the login rate limit; `state_challenge()` is the hook for a future login-redirect endpoint.
- Configuration adds `HE_AUTH_PROVIDER`, the reserved `HE_SESSION_COOKIE_NAME` / `HE_SESSION_TTL_HOURS`, and `HE_OIDC_ISSUER` / `HE_OIDC_CLIENT_ID` / `HE_OIDC_CLIENT_SECRET_ENV`; the secret is stored only as an environment-variable name.
- `IdentityService.create_user` rejects `role=admin` (`422 ROLE_INVALID`); only seeding an empty database can create the global administrator.

## Alternatives considered

- **Keep password verification inside `IdentityService.login`**: every new provider would edit business service code, defeating the seam; rejected.
- **Fall back to password for an unknown provider**: a deployment typo would masquerade as a working setup, violating fail-fast; rejected.
- **Auto-create users from IdP claims**: it bypasses administrator approval and amplifies mapping mistakes; rejected.
- **Store state on the server**: the deployment is single-instance without shared storage; a signed nonce plus cookie already proves integrity and freshness; rejected.
- **Implement real OIDC exchange now**: it is a non-goal and needs network and secret environments; rejected.

## Consequences

- Until a Cookie/OIDC provider lands, `/api/auth/callback` always returns 501; tests own the 400/401/403/502 branches through an injected provider.
- The bridge only maps external identities to internal token pairs; the opaque `he_session` server-side store for a Cookie provider is still empty.
- The state-cookie writer (login-redirect endpoint) does not exist yet; an integrator must first call the server-side `state_challenge()`.
- External-identity users still need an administrator to set `auth_provider` and `external_subject`; there is no dedicated management UI.
- The unique administrator is enforced in the service layer; direct database writes can still bypass it, and a stronger constraint can be evaluated later.
