# Production data directory StateDirectory and deploy writability guard

English | [中文](m16-01-data-dir-state-directory-deploy-guard.md)

```yaml flow
kind: issue
id: m16-01
milestone: m16
depends: []
priority: P1
status: in-progress
scope:
  - deploy/**
  - .github/workflows/deploy.yml
  - apps/api/**
  - packages/contracts/**
  - docs/**
  - README.md
  - README.en.md
  - README.i18n.yaml
  - scripts/doc-budgets.manifest.json
  - .agents/**
  - plans/**
adr: []
github:
  number: 386
  url: https://github.com/Shadow-Azure/harness-evolution/issues/386
```

## Background

Before reading `SKILL.md`, the production launch wizard creates the `data_dir/target-content` cache directory. When `HE_DATA_DIR` is unset, `data_dir` defaults to `data`, which resolves relative to systemd's `WorkingDirectory=/opt/harness/current/api` inside the release tree. The `harness` service user cannot write there, `mkdir` raises `OSError`, and the error is mapped to `content_unavailable`, so the wizard cannot resolve a skill version. The full problem and evidence live in [issue #385](https://github.com/Shadow-Azure/harness-evolution/issues/385).

## Goals

- systemd creates and authorizes the production data directory through `StateDirectory=`, leaving the release tree read-only and replaceable.
- The deploy pipeline injects an absolute path from the GitHub Environment `vars.HE_DATA_DIR`; an empty value falls back to `/var/lib/harness-evolution/data`.
- `release.sh` validates the path before switching `current`; on failure it neither switches nor restarts, and restores the pre-injection `.env`.
- The API resolves the absolute path, creates the directory, and writes a probe at startup; `/api/health` exposes `data.ok` and returns 503 when unwritable, which makes the deploy roll back.
- Local development keeps the `./data` default and its current behavior.

## Design authority

- [01 §6 Deployment shape and expansion path](../../../plans/fullstack-design/01-architecture.md#6-部署形态与扩展路径): single-instance SaaS process, directory, and release boundaries.
- [04 §9 Configuration inventory](../../../plans/fullstack-design/04-backend-architecture.md#9-配置项清单): semantics of `HE_DATA_DIR`.
- [07 §9 Cross-cutting implementation](../../../plans/fullstack-design/07-backend-implementation.md#9-横切实现): the data directory must exist and be writable and is created at startup.
- [issue #385](https://github.com/Shadow-Azure/harness-evolution/issues/385): symptoms, root cause, and option A's Definition of Done.

## Implementation

**Deployment unit and bootstrap**

- `deploy/harness-api.service` gains `StateDirectory=harness-evolution`; systemd creates `/var/lib/harness-evolution` and chowns it to `harness` at service start.
- `deploy/bootstrap-server.sh` installs or updates the unit idempotently (`install` + `daemon-reload` + `enable`) and creates `/var/lib/harness-evolution` as root, so the first initialization already leaves a writable directory.

**Configuration injection**

- Generalize `deploy/inject-eval-config.py` into `deploy/inject-config.py`: accept any `KEY <base64>` line and add `--backup <path>` to snapshot `.env` before the atomic rewrite.
- `deploy.yml` reads `vars.HE_DATA_DIR`, using the absolute default when empty; it injects it together with the evaluation config and backs up to `/opt/harness/shared/.env.bak.<sha>` first.

**Pre-deploy validation and rollback**

- Before switching `current`, `release.sh` validates that `HE_DATA_DIR` is non-empty, absolute, free of whitespace/newlines and `..`, outside `/opt/harness/current` and `/opt/harness/releases`, and either an existing directory writable by the owner or covered by the unit's `StateDirectory=`.
- A failed validation prints the path and reason and exits without switching `current`; every failure path restores the pre-injection `.env`.
- A health failure restores `.env` before restarting the previous release so bad values do not survive rollback.

**API and contracts**

- `app/config.py`: in production `data_dir` must be absolute, otherwise configuration validation fails.
- Add a data-directory probe: resolve the absolute path, run `mkdir(parents=True, exist_ok=True)`, create and delete a write probe, and log the final path and failure reason (never exposed over HTTP).
- `/api/health` gains `data: {ok: bool}` and returns 503 when `data.ok` or `db.ok` is false; sync the `HealthResponse` contract and generated types.

**Docs**

- Add production prerequisites to `README.md` / `README.en.md`; document the data directory, `StateDirectory`, path constraints, and migration in `docs/deployment.md` / `.en.md`; add `HE_DATA_DIR` to `deploy/env.production.example`.

## Implementation steps

1. Update the unit, bootstrap, and deploy workflow; generalize the config injector and wire `vars.HE_DATA_DIR`.
2. Add path validation, `.env` backup/restore, and rollback ordering to `release.sh`.
3. Implement API data-directory resolution, the startup write probe, production absolute-path validation, and health `data.ok`.
4. Regenerate contracts and add unit tests plus configuration-error drills.
5. Update the bilingual docs, env template, and Agent Note; record the pairing hashes.
6. Run focused tests and gates, open the PR, and fix according to CI.

## Dependencies and boundary

- Dependencies: none. Option A's one-time root action happens in the updated bootstrap; routine deploys need no root.
- Non-goals: no root helper or wider deploy sudo, no unit installation in routine deploys, no change to body-hash or target-revision resolution, no data migration tooling, and no frontend UI change.

## Verification

```sh
pnpm test:api
pnpm contract:check
pnpm lint:docs
pnpm verify:flow
bash -n deploy/bootstrap-server.sh deploy/release.sh
```

- A production setting with a relative `HE_DATA_DIR` fails configuration validation with a message that names the path rule.
- An unwritable directory makes `/api/health` return 503 with `data.ok=false`; a writable one returns 200.
- A relative path, a path inside the release tree, or an unauthorized path makes `release.sh` exit before switching `current`.
- The contract snapshot and generated types contain `data.ok`, and `contract:check` reports no drift.

## Acceptance

- Misconfiguration fails during deploy with the concrete path and reason, and the current release keeps serving.
- Health reflects data-directory writability; an unwritable directory rolls the deploy back and restores `.env`.
- With a valid path, systemd/bootstrap creates and authorizes the directory, and the wizard resolves `v7.0.2` without `content_unavailable`.
- Local development keeps the `./data` default; tests cover a relative path, a release-directory path, and an unwritable directory.
- Docs and the env template stay in sync and pass the bilingual pairing gate.

## Gates and CI

- `pnpm test:api`, `pnpm contract:check`, `pnpm lint:docs`, `pnpm verify:flow`, `pnpm verify:flow-online`.
- New tests cover production path validation, writable/unwritable probes, and the health 503 path.
- The PR title and commit subjects reference this issue's GitHub number.

## Non-goals

- Not fixing the #382 version-selection UI problem.
- Not migrating existing `target-content`/`repos`/`workspaces` data; the docs state that a path change is a manual migration.
- Not writing paths into secrets or exposing the data-directory absolute path and failure details in unauthenticated HTTP responses.
