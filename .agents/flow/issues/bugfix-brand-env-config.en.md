# Brand name and subtitle configurable via .env with current defaults

English | [中文](bugfix-brand-env-config.md)

```yaml flow
kind: issue
id: bugfix-54
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - .agents/flow/issues/bugfix-brand-env-config*
  - .agents/notes/**
  - .env.example
  - apps/api/app/**
  - apps/api/tests/**
  - packages/contracts/**
  - apps/web/**
  - tests/e2e/**
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - plans/**
  - plans/fullstack-design/05-api-design.md
  - plans/fullstack-design/08-frontend-implementation.md
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/implemented/feature/2026-11-25-brand-env-config.md
github:
  number: 594
  url: https://github.com/Shadow-Azure/harness-evolution/issues/594
```

## Background

The brand area at the top-left of the shell (the boxed region in the discussion screenshot) currently renders `Harness Evolution` and 「轨迹诊断与自进化」 as fixed text: the brand link in `apps/web/src/components/layout/TopNav.vue`, the login left column in `apps/web/src/pages/login/Index.vue`, the password-change card in `apps/web/src/pages/login/ChangePasswordCard.vue`, the `<title>` in `apps/web/index.html`, and the brand link's `aria-label` are all hard-coded. A deployment that wants another site name must edit source and rebuild.

Production `.env` is injected into the API by systemd's `EnvironmentFile=/opt/harness/shared/.env`; the web bundle is built in CI and synced to the server, so the build environment cannot read the server `.env`. "Configured through `.env`" therefore requires the API to read the values at runtime and hand them to the browser through a public endpoint; when unset, the defaults must be byte-for-byte the current copy.

## Goals

- Add two optional environment variables to the API: `HE_BRAND_NAME` (brand name, default `Harness Evolution`) and `HE_BRAND_SUBTITLE` (subtitle, default `轨迹诊断与自进化`); an empty or whitespace-only value counts as unset and falls back to the default.
- Add the public read-only endpoint `GET /api/app-config` returning the brand name and subtitle without authentication; the login page and the top bar consume the same values.
- The web app fetches the configuration once before mounting, and the top bar, login page, forced password-change card, and browser `<title>` all use it; a failed or invalid response keeps the current defaults and never blocks page load.
- The copy and `aria-label` of an unconfigured deployment stay identical to today, and the existing tests keep passing against the current defaults.

## Design authority

- [05 §4.1 Base endpoints: health check and authentication](../../../plans/fullstack-design/05-api-design.md#41-基础端点健康检查与鉴权): the public endpoint list and the public boundary of `/api/health`; `/api/app-config` follows the same convention.
- [08 §4 Login page, forced password change, and top-bar user area](../../../plans/fullstack-design/08-frontend-implementation.md#4-登录页强制改密与顶栏用户区pageslogin): the current brand surfaces on the login left column, the password-change card, and the top bar.
- [03 §8.1 Layers and inventory](../../../plans/fullstack-design/03-frontend-architecture.md#81-分层与清单): `TopNav.vue` is the navigation and brand slot of the global shell.
- [Deployment · Configuration injection](https://github.com/Shadow-Azure/harness-evolution/blob/main/docs/deployment.en.md#config-injection): the `.env` injection path and the deployment boundary that keeps the real `.env` out of the repository.

## Implementation

### API and contracts

- `Settings` gains `brand_name` and `brand_subtitle`, whose defaults are the current copy; a before validator normalizes empty strings and whitespace-only values to the defaults and strips other values.
- Add `apps/api/app/api/app_config.py`; `GET /api/app-config` returns `{"brand": {"name": ..., "subtitle": ...}}`; the response model uses `extra="forbid"` and the router is registered in `apps/api/app/main.py`.
- Add `/api/app-config` to the public path set in `apps/api/app/middleware/auth.py` so it is readable without a session; the change adds no database table and writes no audit record.
- Follow the generated-contract chain: `pnpm contract:generate` updates `packages/contracts/openapi.json` and the generated types, and `packages/contracts/src/index.ts` exports `AppConfigResponse`.

### Frontend assembly

- Add `apps/web/src/api/appConfig.ts` with fallback defaults, responsible for the request and response validation; validation failures use the defaults.
- `bootstrapApp` loads the brand configuration once before mounting and writes it into a Pinia store (or an equivalent singleton), also setting `document.title = brand.name`; a failed load is caught and mounting continues with the default copy.
- `TopNav.vue` reads the store for the brand link's `aria-label`, `<strong>`, and `<small>`; `pages/login/Index.vue` and `pages/login/ChangePasswordCard.vue` read the same store for the brand name and subtitle, while the password-change card's 「首次登录」 copy stays unchanged.
- `apps/web/index.html` keeps `Harness Evolution` in `<title>` as the pre-load default and the app overwrites it after loading; a long brand name is truncated with an ellipsis and does not squeeze navigation or the user area at a 390px viewport.

### Configuration and documentation

- `.env.example` adds commented `HE_BRAND_NAME` and `HE_BRAND_SUBTITLE` lines under the optional "network and site" group, documenting the defaults, the blank-value fallback, and that a restart of `harness-api` is required after a change.
- The public endpoint list and §4.1 of `plans/fullstack-design/05-api-design.md` gain `GET /api/app-config`; the brand description in §4 of `plans/fullstack-design/08-frontend-implementation.md` notes it can be overridden by env.
- Following `.agents/notes/README.md`, add `implemented/feature/2026-11-25-brand-env-config.md` recording the trade-off between "API runtime configuration plus a public endpoint", "build-time Vite env", and "nginx injection", and fill the path into this issue's `adr`.

## Implementation steps

1. Add the two fields and their normalization tests in `apps/api/app/config.py`, covering unset, empty, whitespace-only, and ordinary values.
2. Add the `app_config` route, the public path, and `apps/api/tests/test_app_config.py` (a token-less request returns 200 and the fields match `Settings`); run `pnpm contract:generate` and review the contract diff.
3. Add the web API client, the store, and the `bootstrapApp` assembly with the document title; add unit tests for success, failure, and missing fields.
4. Switch the top bar, login page, and password-change card to the store; update the existing hard-coded assertions and add a rendering test for a long brand name and a 390px viewport.
5. Update `.env.example`, the 05/08 design notes, and the Agent Note; add a real-browser E2E case covering both the default and configured values.
6. Run this issue's verification commands and screenshots, and record both the "unconfigured" and "configured" evidence in the PR description.

## Dependencies and boundary

- No prerequisite issue dependency; no database migration, authentication-model change, or new deployment Secret.
- The brand is read once when the API starts; a `.env` change requires a `harness-api` restart and there is no runtime hot reload.
- The delivery boundary is the brand name and subtitle text; the brand mark graphic, favicon, login capability copy, and footer copy do not change with `.env`.

## Verification

```sh
pnpm test:api -- tests/test_app_config.py
pnpm test:web
pnpm contract:check
HE_BRAND_NAME='Acme Diagnostics' HE_BRAND_SUBTITLE='Acme Self-Evolution' pnpm test:e2e -- 'brand'
```

- `test_app_config.py`: unset, empty, and whitespace-only inputs return the current defaults, while configured values come back unchanged; `GET /api/app-config` returns 200 without a token.
- Web unit tests: a failed request keeps the default brand; configured values render in the top bar, login page, and `<title>`; the password-change card's brand name updates while 「首次登录」 stays unchanged.
- E2E: the same build shows the current copy and the configured copy in the top bar, login page, and `document.title` under the default environment and under launch arguments carrying `HE_BRAND_NAME` and `HE_BRAND_SUBTITLE`; there is no horizontal overflow at 390px.

## Acceptance

1. With no new variables configured, the top bar, login page, password-change card, `aria-label`, and browser title are byte-identical to today, and the existing E2E assertions need no renaming.
2. After configuring both variables and restarting, those surfaces show the new brand name and subtitle, and `GET /api/app-config` returns the same pair.
3. Configuring only `HE_BRAND_NAME` leaves the subtitle at the current default; empty and whitespace-only values never produce an empty brand.
4. `GET /api/app-config` requires no login; an endpoint failure or invalid response still loads the app and falls back to the current copy.
5. A long brand name (at least 24 characters) is truncated or ellipsized at 1408px and 390px viewports without covering navigation, the user menu, or the demo badge.

## Gates and CI

- Contracts: `pnpm contract:check` must show no diff; the new public path updates the OpenAPI snapshot and generated types.
- Web/API: `pnpm lint:web`, `pnpm typecheck:web`, `pnpm lint:api`, `pnpm typecheck:api`, and the matching test jobs pass.
- Documentation: run `pnpm verify:docs` after the `.env.example` and design-note changes, and let `pnpm lint:docs` pass for the new Agent Note.
- Process: the issue is ready, commits and the PR title carry `(#N)`; the PR links the `Bugfix 问题修复` milestone, and `pnpm verify:flow` plus `pnpm verify:flow-online` run before merge.
- UI change: the PR description attaches same-viewport, same-theme before (current copy) and after (configured copy) screenshots naming the baseline and candidate commits.

## Non-goals

- Do not make the brand mark graphic, favicon, login capability copy, or footer configurable.
- Do not introduce per-workspace, per-role, or per-user branding, and do not add an admin branding settings page.
- Do not change the top-bar layout, navigation, spacing, or design tokens.
- Do not support hot-reloading brand configuration at runtime; a `.env` change requires an API restart.
