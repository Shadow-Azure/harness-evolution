# Agent Note: Brand Name and Subtitle as API Runtime Configuration

Status: implemented

English | [中文](2026-11-25-brand-env-config.md)

## Problem

The top bar, login page, forced password-change card, and browser title hard-code the brand copy in the web source. Production `.env` is injected into the API by systemd, while the web bundle is built in CI and synced to the server, so the build environment cannot read the server `.env`; a deployment that wants another site name must edit source and rebuild.

## Decision

At startup the API reads `HE_BRAND_NAME` / `HE_BRAND_SUBTITLE` into `Settings` and normalizes unset, `None`, empty-string, and whitespace-only values to the built-in defaults (`Harness Evolution` / 「轨迹诊断与自进化」), using configured values with surrounding whitespace stripped. The public read-only endpoint `GET /api/app-config` returns `{"brand":{"name","subtitle"}}` without authentication, like `/api/health`, and writes neither database rows nor audit records. Before mounting, `bootstrapApp` fetches the configuration once and writes it into the Pinia `appConfig` store; success overrides the brand and sets `document.title`, while a failed or invalid response keeps the defaults, mounts normally, and never throws. The brand slots in the top bar, login page, and password-change card read the same store, and long brand names are truncated with an ellipsis.

## Alternatives considered

- Build-time Vite env: rejected because the CI build cannot read the server `.env`; one artifact could not carry a per-deployment brand, which would push configuration back into source.
- nginx `sub_filter` / template injection: rejected because it requires per-deployment HTML rewrite rules, conflicts with escaping and SPA title updates, and cannot cover the login page or password-change card state rendering.
- Runtime hot reload: rejected because it needs file watching or config polling for what is a deployment-level copy change; restarting `harness-api` is sufficient and predictable.
- Admin branding page or per-workspace brands: rejected as beyond this issue's delivery boundary and as new persistence and permission surface.

## Consequences

Changing `.env` requires restarting `harness-api` to take effect. The default brand exists in both `apps/api/app/config.py` and `apps/web/src/api/appConfig.ts`, so the two sides must stay in sync; API, store, and component tests guard against drift. The public endpoint adds one unauthenticated read surface, but it exposes only brand text, not deployment paths or credentials. Long brand names rely on CSS truncation; below 640px the top bar hides the subtitle and brand text and keeps only the mark, and the existing breakpoints keep the 390px viewport free of horizontal overflow.
