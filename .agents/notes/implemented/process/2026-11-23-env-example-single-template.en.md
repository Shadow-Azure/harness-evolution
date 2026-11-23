# Agent Note: Production .env template lives at the repository root

Status: implemented

English | [中文](2026-11-23-env-example-single-template.md)

## Problem

Production `.env` is read by systemd through `EnvironmentFile=`. A missing `HE_JWT_SECRET` makes the service refuse to start, and missing administrator credentials leave a first deployment without a login-capable account. `deploy/env.production.example` groups variables by network, data, Git, and other domains, mixing required and optional entries; an operator must cross-check `apps/api/app/config.py` to know which values cannot be empty. The user needs a `.env.example` that puts required fields first and explains every field. systemd also does not support trailing comments on assignment lines, so explanations cannot sit at the end of the value line.

## Decision

The repository-root `.env.example` is the single production `.env` template, with required fields first and optional fields after them. The line after each assignment uses `# 必填｜...` or `# 选填｜...` to explain the value, purpose, default, and constraints. `deploy/env.production.example` is removed, and the template links in the deployment docs, bootstrap, and playbook point at the root template. `.gitignore` keeps ignoring `.env` / `.env.*` and exempts only `.env.example`. Required fields stay active, optional fields are commented out by default with a leading `#`, and an operator uncomments only the integrations they use. Comments stay on standalone lines so the template can be copied directly to the server `.env` without changing any value.

## Alternatives considered

Keep `deploy/env.production.example` and add a root explanation file: the two templates would drift as Settings evolve, and an operator would still have to decide which one is copyable. Put required/optional notes at the end of assignment lines: systemd folds everything after `#` into the value, so fields such as `HE_HOST` and `HE_DATA_DIR` would fail validation and the template would no longer be usable. Generate the template from `Settings`: defaults and field names are mechanical, but "why required" and "administrator credentials are only needed on first deployment" cannot be derived from types, and the deployment injection semantics still need human comments. Only edit the old template without moving it: the user explicitly asked for `.env.example`, and the old path hides the template under `deploy/` instead of giving the repository a root entry point.

## Consequences

The template has one home, so adding or removing a Settings field only requires updating the root `.env.example` and the deployment-doc links. The default template enables only required fields, so an operator cannot accidentally set an optional field to an unintended value. Historical `plans/` review records may still mention the old path; they are process snapshots and are not part of the link gate. Standalone comments let the template be copied directly; if someone moves a note back to a trailing comment, systemd will treat it as part of the value and review must catch it. Build metadata such as `HE_VERSION` / `HE_PHASE` is intentionally not expanded, so internal health fields are not mistaken for deployment requirements.
