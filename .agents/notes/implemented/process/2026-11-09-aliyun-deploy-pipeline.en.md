# Agent Note: Direct single-host deployment channel on Alibaba Cloud

Status: implemented

English | [中文](2026-11-09-aliyun-deploy-pipeline.md)

## Problem

The service had only a local `pnpm dev` entry point; CI carried quality gates but no delivery channel, and the demo/trial environment needs to sit on the public internet via Alibaba Cloud. Constraints: single maintainer, domestic ECS hosts connect to GitHub poorly, tight budget, and design doc §6 already locks the single-instance SaaS shape (uvicorn 8787, MySQL 8 primary, nginx serving static assets, self-hosted account JWT).

## Decision

The delivery channel is CI-build-plus-rsync bare-metal deployment: after CI (`ci-ok`) goes green, GitHub Actions pushes the frontend bundle and API source to an ECS release directory over SSH with a key; server-side `deploy/release.sh` installs dependencies, runs Alembic migrations (injecting `HE_DB_URL` into a copy of `alembic.ini` at release time — the repo copy stays empty), atomically switches the `current` symlink, restarts systemd, and probes `/api/health`, rolling back to the previous release on a failed probe. MySQL is self-hosted on the same ECS (bootstrap script creates the database and account); authentication uses an ed25519 private key for the deploy user stored in GitHub Actions Secrets, with the deploy user's sudoers narrowed to `systemctl restart/start harness-api`. The service runs as the `harness` system user, uvicorn binds only 127.0.0.1, and the only public entries are nginx 80/443.

## Alternatives considered

- Docker images + ACR: best reproducibility, but adds a registry, Dockerfiles, and image versioning; maintenance cost exceeds the benefit at this stage, kept as a scaling path.
- Server-side git pull: domestic ECS reaches GitHub slowly and unreliably, and it exposes building to the server; CI builds and pushes artifacts instead.
- OSS artifact relay: one more hop of configuration and credentials; rsync over SSH is simpler and more direct for a single host.
- RDS MySQL: zero ops but a fixed monthly bill; self-hosted same-host MySQL during the solo demo period, migration cost is one `HE_DB_URL` switch.

## Consequences

- Rollback semantics are symlink revert plus restart, with the API unavailable for under a minute; forward-fixing a bad migration is not automated (Alembic downgrade stays out of the automatic flow).
- No horizontal scaling on one host: the in-memory SSE bus and in-process worker assume a single instance; scaling needs a new issue per the §6 path.
- HTTPS certificates are installed and renewed manually (no TLS before a domain is bound); the certificate lands after ICP filing and traffic then narrows to 443.
- A leaked deploy-user private key equals production access; Secrets rotation and the `production` environment approval are the only additional guardrails.
