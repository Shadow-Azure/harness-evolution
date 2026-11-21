# Deployment

English | [中文](deployment.md)

Production is a single-instance Alibaba Cloud SaaS: nginx serves the built frontend and reverse-proxies `/api` to a local uvicorn (127.0.0.1:8787), with MySQL 8 on the same host. Releases run through GitHub Actions: after main's CI is green (`ci-ok`), `Deploy` builds the frontend, pushes the release, migrates, switches the `current` symlink, and restarts, rolling back when the probe fails. The design authority is [plans/fullstack-design/01-architecture.md §6](../plans/fullstack-design/01-architecture.md).

## Cloud resources

| Resource | Configuration |
|---|---|
| ECS | Single instance, Ubuntu 22.04/24.04, 2 vCPU/4 GiB (2 GiB needs swap), bandwidth ≥3 Mbps |
| MySQL 8 | Same host (apt install), database `harness_evolution`, user `harness@127.0.0.1` |
| Security group | Open 22/80/443; 8787 never public |
| Domain | Optional; IP + HTTP first, then HTTPS and ICP filing |

## Server layout

| Path | Contents |
|---|---|
| `/opt/harness/releases/<sha>/` | One release (`api/` source + `web/` static bundle) |
| `/opt/harness/current` | Symlink to the live release; working directory of nginx and systemd |
| `/opt/harness/shared/.env` | Production `HE_*` config (template: [deploy/env.production.example](../deploy/env.production.example)) |
| `/opt/harness/shared/venv/` | Shared Python virtual environment |
| `/opt/harness/shared/config/` | Deployment configs pushed by the pipeline (systemd/nginx/release.sh) |
| `/var/lib/harness-evolution/` | Server data directory created and authorized by systemd `StateDirectory=` for `harness`; `HE_DATA_DIR` points inside it |

## First-time bootstrap

Bootstrap is done by [deploy/bootstrap-server.sh](../deploy/bootstrap-server.sh) (base packages, Python 3.12, users, MySQL database and account, nginx and systemd); the step-by-step guide lives in [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md).

## GitHub configuration

| Name | Type | Contents |
|---|---|---|
| `ALIYUN_HOST` | Secret | ECS public IP |
| `ALIYUN_USER` | Secret | SSH user (`deploy`) |
| `ALIYUN_SSH_KEY` | Secret | deploy user's ed25519 private key |
| `ALIYUN_SSH_PORT` | Variable | SSH port (default 22) |
| `HE_DATA_DIR` | Variable | Absolute data-directory path; empty uses `/var/lib/harness-evolution/data` |
| `XRAY_CONFIG` | Environment Secret | Optional: complete Xray JSON (VLESS outbound plus loopback mixed inbound), see [Git egress proxy](git-proxy.en.md) |
| `production` | Environment | Protective environment for the deploy job; can require approval |

Only the private key lives in GitHub; its public half sits in `deploy`'s `authorized_keys` on the server; runtime secrets live only in `/opt/harness/shared/.env`, and the proxy config lives only in a `0600` server file.

## Config injection

The data directory and evaluation config share one channel into the server `.env`: `Deploy` takes an absolute path from the GitHub Environment `vars.HE_DATA_DIR` (the default applies when empty), and evaluation-platform secrets (`HE_EVAL_MODE`/`HE_EVAL_BASE_URL`/`HE_EVAL_API_KEY`) arrive from GitHub Secrets; `apiKeyRef` stores only an environment-variable name and the step is skipped when absent. Git push credentials ride the same channel: `HE_GIT_PUSH_PROVIDER` is always written, `HE_GIT_PUSH_TOKEN` is unset when empty, and `GIT_ASKPASS` points at `/opt/harness/shared/git-askpass.sh`. Values travel base64-encoded and `inject-config.py` writes them atomically while keeping `.env` at 0600, backing up `.env.bak.<sha>` first; decode failures warn and skip, disk-write failures abort the release. Steps: [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md); template: [deploy/env.production.example](../deploy/env.production.example).

## Claude Code

Before switching `current`, the deploy pipeline installs Claude Code for the `deploy` user and writes model configuration from GitHub Secrets; the runner fetches the package and the server only extracts it, with no `claude.ai` access, root, or Node.js. The three secrets, MiniMax setup, verification and rollback live in [Claude Code operations](claude-code.en.md).

## Release and rollback

- Trigger: push to main → CI green → `Deploy`; `workflow_dispatch` also available.
- Behavior: [deploy/release.sh](../deploy/release.sh) validates the data directory → installs dependencies → `alembic upgrade head` → switches the `current` symlink → restarts harness-api → probes `/api/health` (up to 60 seconds).
- Rollback: on a failed probe it restores `.env` first, then returns the symlink to the previous release and restarts; the server keeps the latest 5 releases and 5 `.env` backups.
- Migrations are idempotent: repeated releases have zero side effects on applied migrations.

## Data directory and writability check

Production `HE_DATA_DIR` must be an absolute path outside the release tree, defaulting to `/var/lib/harness-evolution/data`; `StateDirectory=harness-evolution` in `deploy/harness-api.service` lets systemd create it and chown it to `harness` on every start, and bootstrap also creates it. Before switching `current`, `release.sh` validates that the path is non-empty, absolute, free of whitespace/newlines and `..`, outside `current` and `releases`, and owned by `harness:harness` or covered by the unit's `StateDirectory=`; it exits immediately on failure while the current release keeps serving.

The API resolves the absolute path, creates the directory, and writes a probe at startup; when it is not writable `/api/health` returns 503 (`data.ok=false`), so a failed release probe rolls back. A path change is a data migration: `target-content`, `repos`, and `workspaces` do not follow, so stop the service, move the directories, and change `vars.HE_DATA_DIR`. Enabling `StateDirectory=` on an existing environment needs one root-run bootstrap (or installing the unit followed by `daemon-reload`); that is per-environment initialization, not a routine deploy.

## Git egress proxy

When production access to GitHub is unstable, a local Xray/VLESS proxy that serves git subprocesses only can be enabled; its configuration comes from the Environment Secret `XRAY_CONFIG`, and both deploy and runtime fall back to direct access when the proxy is unavailable. See [Git egress proxy](git-proxy.en.md).

## Git workspaces and pushes

Evolution run workspaces cache the target ref and clone from it; the push target is controlled by `HE_GIT_PUSH` / `HE_GIT_PUSH_URL`. See [Git workspaces and pushes](git-workspace.en.md) for the cache, single-ref clone, push credential policy, and per-operation proxy observability.

## Upstream health and drift logs

With `HE_UPSTREAM_BASE_URL` / `HE_UPSTREAM_TOKEN` configured, pulls emit `upstream.health` / `version_drift` / `contract_drift` logs with `key='value'` fields containing only enums, counts, and major numbers, never bodies, session ids, or credentials. Per-session failures stay in `sync_runs.errors`; the scheduler only replays stored payloads, so a failed fetch needs `POST /api/acquisition/pull` with `sessionIds`.

## Troubleshooting

- A bad-case detail response of 409 `BAD_CASE_SESSION_PENDING` or 503 `BAD_CASE_SESSION_UNAVAILABLE` means the case was reported but its trace is not ready; it is not data loss. Check the trace-query configuration, or ask the reporter to supply `sessionSource`.

## External-table read privileges and contract logs

The read path needs SELECT only on `bad_cases`, `bad_case_analysis`, and `probe_reports`; reporting, catalog sync, and attribution writes also need INSERT/UPDATE (never external-row deletes). After startup the API checks column and type contracts every five minutes by default (`HE_EXTERNAL_CONTRACT_CHECK_INTERVAL_SECONDS` tunes it) and emits `external.contract_check`, `external.contract_drift`, and `external.row_drift`. Failed reads return a stable 503 (`EXTERNAL_SCHEMA_DRIFT` / `EXTERNAL_READ_FORBIDDEN` / `EXTERNAL_READ_FAILED`); `external.read_failed` carries only table names, dialect, error classes, driver codes, and the stable code, never SQL or parameters.
