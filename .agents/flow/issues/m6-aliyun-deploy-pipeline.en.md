# Automated frontend and backend deployment to Alibaba Cloud ECS via GitHub Actions

English | [中文](m6-aliyun-deploy-pipeline.md)

```yaml flow
kind: issue
id: m6-22
milestone: m6
depends:
  - m6-09
priority: P1
status: ready
scope:
  - .github/workflows/**
  - deploy/**
  - docs/**
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 198
  url: https://github.com/Shadow-Azure/harness-evolution/issues/198
```

## Background

The service currently runs only locally via `pnpm dev`; CI has PR gates and the main-push quality lanes (`ci-ok`) but no delivery channel at all. Design doc §6 already defines the deployment shape — "single-instance SaaS + uvicorn 8787 + MySQL 8 primary + nginx serving the static frontend" — but it has never been realized. To put a demo/trial environment on a public Alibaba Cloud host, we need a frontend-and-backend pipeline that publishes automatically when main goes green, with no manual SSH anywhere in the loop.

## Goals

- After a push to main with `ci-ok` green, GitHub Actions automatically: builds the `apps/web` bundle → rsyncs it to the ECS host → runs Alembic migrations → restarts the systemd service → health-checks, rolling back to the previous release on failure.
- Server-side configuration templates land in the repo (systemd unit, nginx site, remote deploy script, `.env` example), so a fresh ECS can be bootstrapped reproducibly from the docs.
- Secrets live in exactly two places: GitHub Actions Secrets (SSH private key) and the server-local `.env` (`HE_*`); no real credentials ever enter the repository.

## Design authority

- [plans/fullstack-design/01-architecture.md §6 Deployment shape and scaling path](../../../plans/fullstack-design/01-architecture.md): single-instance SaaS, `uvicorn app.main:app --host 0.0.0.0 --port 8787`, static frontend served by nginx, CORS set to the production domain — the target shape is that section's "now" column, with none of the scaling-path items enabled.
- [plans/fullstack-design/04-backend-architecture.md](../../../plans/fullstack-design/04-backend-architecture.md): MySQL 8 is the production primary and SQLite is test-only; `HE_DB_DIALECT`/`HE_DB_URL` is the environment surface for dialect switching.
- Where implementation conflicts with the linked sections, the linked sections prevail; this issue only adds a delivery channel and changes no application behavior.

## Implementation

- `.github/workflows/deploy.yml`: triggered via `workflow_run` after CI succeeds (or by reusing the `ci-ok` aggregate verdict); builds the frontend bundle, pushes a release directory over rsync with an SSH key, runs the remote deploy script, all gated behind `environment: production`.
- `deploy/harness-api.service`: systemd unit keeping uvicorn resident (`apps/api/.venv/bin/python -m app`, EnvironmentFile pointing at `/opt/harness/shared/.env`).
- `deploy/nginx-harness.conf`: static hosting of the dist behind the `current` symlink, `/api` reverse-proxied to `127.0.0.1:8787`, SSE location with buffering off.
- `deploy/release.sh`: server-side script — install/update API dependencies, `alembic -x sqlalchemy.url="$HE_DB_URL" upgrade head`, switch the symlink, restart the service, `curl /health` probe, roll back on failure.
- `deploy/env.production.example`: the production `HE_*` environment checklist (`HE_JWT_SECRET`, `HE_DB_URL`, `HE_CORS_ORIGINS`, `HE_ADMIN_USERNAME`/`HE_ADMIN_PASSWORD`, etc.), values left empty.
- `docs/deployment.md` (plus English side): Alibaba Cloud resource checklist (ECS/RDS/security group/domain + ICP/certificate), GitHub Secrets setup, first-time bootstrap and rollback manual.

## Implementation steps

1. Prepare Alibaba Cloud resources (ECS, RDS MySQL, security group, domain and certificate) following the `docs/deployment.md` checklist.
2. Bootstrap the server: Python 3.12, nginx, a `deploy` user with the SSH public key, `/opt/harness/{releases,shared,current}` directories and the `.env`.
3. Configure repo Secrets (host, user, private key, port) and the `production` environment approval.
4. Author `deploy.yml`, the `deploy/` templates, and the bilingual deployment docs.
5. Trigger the first release manually to verify the full chain, then rehearse one failure rollback.

## Dependencies and boundary

- Depends on: m6-09 (CI lane split and the `ci-ok` aggregate gate; deploy hangs off it).
- Delivery boundary: only the pipeline, server configuration templates, and docs; no changes to any `apps/` or `packages/` code or contracts. Scope-extension note: `plans/**` (deployment playbook and the PR review doc land in plans/ per docs/review.md) and `scripts/doc-budgets.manifest.json` (word-budget registration for the new resident doc, per docs/AGENTS.md) are required by this issue's implementation.
- Non-goals: see the dedicated section below.

## Verification

```sh
pnpm verify:flow
pnpm verify:docs
```

- `verify:flow` reports all lanes passing; `verify:docs` reports the documentation gates passing (new-doc word budgets registered).
- Delivery-channel verification (once the Alibaba Cloud resources exist): push main → the `deploy` workflow on the Actions page goes green; on the server `curl -sf http://127.0.0.1:8787/health` returns 200 with a `phase` field; browsing `https://<domain>` allows login and Session viewing.

## Acceptance

- From merge to a reachable new version after a main push, zero manual SSH.
- When the health check fails, automatic rollback to the previous release keeps the API unavailable for under a minute.
- Only 80/443 are public; 8787 is reachable only on the loopback path (via the nginx reverse proxy).
- Migrations are idempotent: two consecutive deployments produce no duplicate changes or failures.
- A fresh ECS can be bootstrapped from scratch following the docs.

## Gates and CI

- `verify:flow --diff`: PR and commit titles carry `(#N)`, and the diff lands inside the registered scope.
- `verify:docs`: the new deployment doc registers a word budget with both language sides paired.
- `deploy.yml` does not run inside PR lanes (it fires only after CI succeeds on main); its yml syntax is validated during implementation with a local `node --check` equivalent and the first real run.

## Non-goals

- No Docker images or ACR (container registry) — a later evolution path, beyond the §6 scaling table.
- No multi-instance horizontal scaling, CDN, or Redis pub/sub SSE bus.
- No automatic HTTPS certificate renewal (first issuance is a manual Alibaba Cloud free certificate; renewal goes into the docs).
- No changes to application code, contracts, or gate scripts.
