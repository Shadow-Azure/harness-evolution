# Deployment

English | [中文](deployment.md)

Alibaba Cloud hosts nginx, uvicorn (127.0.0.1:8787) and MySQL 8 on one instance. Nginx serves the built frontend and proxies `/api`. The design authority is [plans/fullstack-design/01-architecture.md §6](../plans/fullstack-design/01-architecture.md).

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
| `/opt/harness/shared/.env` | Production `HE_*` config (template: [.env.example](../.env.example)) |
| `/opt/harness/shared/venv/` | Shared Python virtual environment |
| `/opt/harness/shared/config/` | Deployment configs pushed by the pipeline (systemd/nginx/release.sh) |
| `/var/lib/harness-evolution/` | Server data directory created and authorized by systemd `StateDirectory=` for `harness`; `HE_DATA_DIR` points inside it |

## First-time bootstrap

Bootstrap is done by [deploy/bootstrap-server.sh](../deploy/bootstrap-server.sh) (base packages, Python 3.12, users, MySQL database and account, nginx and systemd); the step-by-step guide lives in [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md).

## Provision entry

The attribution Skill's `bubblewrap` is a system package; the `deploy` user has no apt/dpkg rights, and routine releases only use `attribution.preflight` as the gate. Existing hosts use a standalone [Provision workflow](../.github/workflows/provision.yml): `workflow_dispatch` + `environment: production`; only a dispatch from `main` runs; modes are `check` / `install` / `dry-run`. It calls [provision-bubblewrap.sh](../deploy/provision-bubblewrap.sh), which only verifies when installed, installs when missing, and runs a namespace probe as `harness`; on Ubuntu 24.04 the AppArmor userns restriction is opened by the profile the script installs at `/etc/apparmor.d/bwrap-userns-restrict` (only for the resolved bwrap path, not the host-wide sysctl); `ATTRIBUTION_BWRAP_MISSING` / `ATTRIBUTION_BWRAP_UNUSABLE` match the preflight codes. The credentials are the `production` environment's `PROVISION_SSH_KEY` (dedicated root private key) and the optional Variable `PROVISION_SSH_USER` (default `root`); see the [deployment playbook](../plans/deploy-aliyun-playbook.md#4-github-仓库配置网页粘贴) for the secret read scope and rotation.

## New-host cloud-init

When creating an ECS instance, use [deploy/cloud-init.yaml](../deploy/cloud-init.yaml) to install the runtime prerequisites at creation; Ubuntu 24.04 still needs one Provision `install` after creation for the profile. The attribution runtime prerequisites live in [deploy/attribution-runtime-prerequisites.list](../deploy/attribution-runtime-prerequisites.list); bootstrap reads it and cloud-init mirrors it.

## CI gate: deployment provisioning contract

`deploy-contract` runs [verify_provisioning_contract.sh](../apps/api/tests/deploy/verify_provisioning_contract.sh) in a clean `ubuntu:24.04` container: the missing-package negative case, the provision install, the `harness` probe, and `attribution.preflight` must pass in order. [test_provisioning_contract.py](../apps/api/tests/deploy/test_provisioning_contract.py) runs with the API suite and statically asserts the prerequisite list, bootstrap/cloud-init/Provision consistency, and the `release.sh` preflight order. `deploy-contract` is in `ci-ok.needs`; branch protection only needs `ci-ok`.

Adding a deployment runtime prerequisite and gate triage are covered in the [deployment playbook](../plans/deploy-aliyun-playbook.md#6-常见问题).

## GitHub configuration

| Name | Type | Contents |
|---|---|---|
| `ALIYUN_HOST` | Secret | ECS public IP |
| `ALIYUN_USER` | Secret | SSH user (`deploy`) |
| `ALIYUN_SSH_KEY` | Secret | deploy user's ed25519 private key |
| `ALIYUN_SSH_PORT` | Variable | SSH port (default 22) |
| `PROVISION_SSH_KEY` | Environment Secret | Dedicated root private key for the `production` environment; see the playbook for its read scope |
| `PROVISION_SSH_USER` | Variable | Optional; Provision SSH user (default `root`, must be root) |
| `HE_DATA_DIR` | Variable | Absolute data-directory path; empty uses `/var/lib/harness-evolution/data` |
| `XRAY_CONFIG` | Environment Secret | Optional: complete Xray JSON (VLESS outbound plus loopback mixed inbound), see [Git egress proxy](git-proxy.en.md) |
| `production` | Environment | Protective environment for the deploy job; can require approval |

Only the private key lives in GitHub; its public half sits in `deploy`'s `authorized_keys` on the server; runtime secrets live only in `/opt/harness/shared/.env`, and the proxy config lives only in a `0600` server file.

## Config injection

The data directory and evaluation config share one channel into the server `.env`: `Deploy` takes an absolute path from the GitHub Environment `vars.HE_DATA_DIR` (the default applies when empty), and evaluation-platform secrets (`HE_EVAL_MODE`/`HE_EVAL_BASE_URL`/`HE_EVAL_API_KEY`) arrive from GitHub Secrets; `apiKeyRef` stores only an environment-variable name and the step is skipped when absent. Git push credentials ride the same channel: `HE_GIT_PUSH_PROVIDER` is always written, `HE_GIT_PUSH_TOKEN` is unset when empty, and `GIT_ASKPASS` points at `/opt/harness/shared/git-askpass.sh`. Values travel base64-encoded and `inject-config.py` writes them atomically while keeping `.env` at 0600, backing up `.env.bak.<sha>` first; decode failures warn, skip, and keep the old value, disk-write failures abort the release. Steps: [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md); template: [.env.example](../.env.example).

### AI Agent configuration

Model review and patch generation take Secrets `AI_AGENT_PROVIDER`, `HE_AI_AGENT_FAILURE_POLICY`, and `HE_PATCH_SOURCE_MODE`: a present, non-empty value is written to `.env`, a missing or empty one is explicitly `--unset`, and the service falls back to the Settings defaults (defaults and allowed values are in the [template](../.env.example)). A newline or carriage return in a value fails the deploy before injection (a skipped value is not a deletion); other keys still warn, skip, and keep their old value on decode failures. When `HE_AI_AGENT_FAILURE_POLICY` is empty it derives from the provider: `degrade` for `fake` and `strict` for every other provider (including the default `claude-code`); under `strict`, a cluster AI failure fails the run explicitly at the cluster stage without fallback values.

`agent-edit` needs a configured provider. The home-less `harness` account reads shared settings via `CLAUDE_CONFIG_DIR`. Set `HE_AI_AGENT_CLAUDE_BIN` to use an existing CLI.

### Attribution runtime

Binding attribution and wizard recomputation share the provider and model. Linux Claude needs `bubblewrap`: existing hosts install it through the [Provision entry](deployment.en.md#provision-entry), and new hosts run Provision `install` once after cloud-init. Deployment checks before migration and the API checks again on startup. Read the reason with `journalctl -u harness-api -g attribution.preflight`. Restart after recovery to resume the original binding. See the [service-account probe and report verification](../plans/deploy-aliyun-playbook.md#验证-skill-归因).

## Claude Code

Before switching `current`, the deploy pipeline installs Claude Code and writes service-level shared configuration: a version directory plus a stable `current` symlink, a 0644 shared `settings.json` without credentials, and `ANTHROPIC_API_KEY` in the 0600 `.env`. The runner fetches the package and the server only extracts it, with no `claude.ai` access, root, or Node.js; a service-user executable/readable preflight runs before the `current` switch. Secrets, MiniMax setup, verification and rollback live in [Claude Code operations](claude-code.en.md).

## Release and rollback

- Trigger: push to main → CI green → `Deploy`; `workflow_dispatch` also available.
- Behavior: [deploy/release.sh](../deploy/release.sh) validates the data directory → installs dependencies → checks the attribution runtime → `alembic upgrade head` → switches the `current` symlink → restarts harness-api → probes `/api/health` (up to 60 seconds).
- Rollback: on a failed probe it restores `.env` first, then returns the symlink to the previous release and restarts; the server keeps the latest 5 releases and 5 `.env` backups.
- Restart drain: the systemd unit uses `KillMode=mixed` + `TimeoutStopSec=45` so the main process receives SIGTERM first; the application waits for in-flight jobs up to `HE_JOB_DRAIN_TIMEOUT_SECONDS` (25 seconds by default), then releases the lease and marks the job `interrupted` for automatic recovery on the next start.
- Migrations are idempotent: repeated releases have zero side effects on applied migrations.

## Data directory and writability check

Production `HE_DATA_DIR` must be an absolute path outside the release tree, defaulting to `/var/lib/harness-evolution/data`; `StateDirectory=harness-evolution` in `deploy/harness-api.service` lets systemd create it and chown it to `harness` on every start, and bootstrap also creates it. Before switching `current`, `release.sh` validates that the path is non-empty, absolute, free of whitespace/newlines and `..`, outside `current` and `releases`, and owned by `harness:harness` or covered by the unit's `StateDirectory=`; it exits immediately on failure while the current release keeps serving.

The API resolves the absolute path, creates the directory, and writes a probe at startup; when it is not writable `/api/health` returns 503 (`data.ok=false`), so a failed release probe rolls back. A path change is a data migration: `target-content`, `repos`, and `workspaces` do not follow, so stop the service, move the directories, and change `vars.HE_DATA_DIR`. Enabling `StateDirectory=` on an existing environment needs one root-run bootstrap (or installing the unit followed by `daemon-reload`); that is per-environment initialization, not a routine deploy.

## Git egress proxy

When production access to GitHub is unstable, a local Xray/VLESS proxy that serves git subprocesses only can be enabled; its configuration comes from the Environment Secret `XRAY_CONFIG`, and both deploy and runtime fall back to direct access when the proxy is unavailable. See [Git egress proxy](git-proxy.en.md).

## Git workspaces and pushes

Run workspaces cache the target ref and clone from it; the provider creates the fork automatically, with `HE_GIT_PUSH_URL` as the no-token fallback. See [Git workspaces and pushes](git-workspace.en.md) for the cache, single-ref clone, push credential policy, and per-operation proxy observability.

## Upstream health and drift logs

With `HE_UPSTREAM_BASE_URL` / `HE_UPSTREAM_TOKEN` configured, pulls emit `upstream.health` / `version_drift` / `contract_drift` logs with `key='value'` fields containing only enums, counts, and major numbers, never bodies, session ids, or credentials. Per-session failures stay in `sync_runs.errors`; the scheduler only replays stored payloads, so a failed fetch needs `POST /api/acquisition/pull` with `sessionIds`.

## Troubleshooting

- A bad-case detail response of 409 `BAD_CASE_SESSION_PENDING` or 503 `BAD_CASE_SESSION_UNAVAILABLE` means the case was reported but its trace is not ready; it is not data loss. Check the trace-query configuration, or ask the reporter to supply `sessionSource`.

## External-table read privileges and contract logs

The read path needs SELECT only on `bad_cases`, `bad_case_analysis`, and `probe_reports`; reporting, catalog sync, and attribution writes also need INSERT/UPDATE (never external-row deletes). After startup the API checks column and type contracts every five minutes by default (`HE_EXTERNAL_CONTRACT_CHECK_INTERVAL_SECONDS` tunes it) and emits `external.contract_check`, `external.contract_drift`, and `external.row_drift`. Failed reads return a stable 503 (`EXTERNAL_SCHEMA_DRIFT` / `EXTERNAL_READ_FORBIDDEN` / `EXTERNAL_READ_FAILED`); `external.read_failed` carries only table names, dialect, error classes, driver codes, and the stable code, never SQL or parameters.
