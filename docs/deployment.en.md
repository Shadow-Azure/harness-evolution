# Deployment

English | [中文](deployment.md)

Production is a single-instance Alibaba Cloud SaaS: nginx serves the built frontend and reverse-proxies `/api` to a local uvicorn (127.0.0.1:8787, resident under systemd), with MySQL 8 on the same host. Releases run through GitHub Actions: after a push to main with CI green (`ci-ok`), the `Deploy` workflow builds the frontend, rsyncs a release to the ECS host, runs migrations, atomically switches the `current` symlink, and restarts the service, rolling back when the probe fails. The design authority is [plans/fullstack-design/01-architecture.md §6](../plans/fullstack-design/01-architecture.md).

## Cloud resources

| Resource | Configuration |
|---|---|
| ECS | Single instance, Ubuntu 22.04/24.04, 2 vCPU/4 GiB (2 GiB needs swap), bandwidth ≥3 Mbps |
| MySQL 8 | Same host (apt install), database `harness_evolution`, user `harness@127.0.0.1` |
| Security group | Open 22/80/443; 8787 never exposed publicly |
| Domain | Optional; IP + HTTP until bound, then add HTTPS and ICP filing |

## Server layout

| Path | Contents |
|---|---|
| `/opt/harness/releases/<sha>/` | One release (`api/` source + `web/` static bundle) |
| `/opt/harness/current` | Symlink to the live release; working directory of nginx and systemd |
| `/opt/harness/shared/.env` | Production `HE_*` config (template: [deploy/env.production.example](../deploy/env.production.example)) |
| `/opt/harness/shared/venv/` | Shared Python virtual environment |
| `/opt/harness/shared/config/` | Deployment configs pushed by the pipeline (systemd/nginx/release.sh) |

## First-time bootstrap

Bootstrap is done by [deploy/bootstrap-server.sh](../deploy/bootstrap-server.sh) (base packages, Python 3.12, users, MySQL database and account, nginx and systemd); the step-by-step guide lives in [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md).

## GitHub configuration

| Name | Type | Contents |
|---|---|---|
| `ALIYUN_HOST` | Secret | ECS public IP |
| `ALIYUN_USER` | Secret | SSH user (`deploy`) |
| `ALIYUN_SSH_KEY` | Secret | deploy user's ed25519 private key |
| `ALIYUN_SSH_PORT` | Variable | SSH port (default 22) |
| `production` | Environment | Protective environment for the deploy job; can require approval |

Only the private key lives in GitHub; its public half sits in the `deploy` user's `authorized_keys` on the server; runtime secrets live only in `/opt/harness/shared/.env`.

## Release and rollback

- Trigger: push to main → CI green → `Deploy`; manual `workflow_dispatch` supported.
- Behavior: [deploy/release.sh](../deploy/release.sh) installs dependencies → `alembic upgrade head` → switches the `current` symlink → `systemctl restart harness-api` → probes `/api/health` (up to 60 seconds).
- Rollback: on a failed probe the symlink returns to the previous release and the service restarts; the server keeps the latest 5 releases.
- Migrations are idempotent: repeated releases have zero side effects on applied migrations.
