# Agent Note: Install system prerequisites through a standalone Provision pipeline

Status: implemented

English | [中文](2026-11-23-provision-bubblewrap-pipeline.md)

## Problem

On Linux the attribution Skill depends on `bubblewrap`, but that is an OS package, not a Python dependency. The production host was initialized before bootstrap included it, so the latest Deploy was stopped by `attribution.preflight`; the previous release keeps serving, but the new version cannot ship. Routine Deploy runs as the `deploy` user, whose sudoers only covers `systemctl` and has no apt/dpkg rights. Giving apt to deploy is equivalent to giving root to the pipeline, while continuing manual SSH package installation is neither repeatable nor auditable and does not cover new hosts.

## Decision

Provisioning of OS packages goes through a standalone `Provision` workflow, decoupled from release:

- `.github/workflows/provision.yml` is triggered only by `workflow_dispatch`, binds the `production` environment, and runs only from `main`; it uses the `production` environment's dedicated root credentials `PROVISION_SSH_KEY` / `PROVISION_SSH_USER` and reuses `ALIYUN_HOST` and `ALIYUN_SSH_PORT`.
- `deploy/provision-bubblewrap.sh` runs idempotently as root: it checks first, only verifies when the package is installed, and runs `apt-get update` plus install only when missing; finally it runs a minimal namespace probe as `harness`. Ubuntu 24.04 restricts unprivileged userns through AppArmor by default; when the probe fails, the script installs `/etc/apparmor.d/bwrap-userns-restrict` to allow only the resolved bwrap executable and retries, without changing the host-wide `kernel.apparmor_restrict_unprivileged_userns`. `--check` is read-only and `--dry-run` only prints the plan; error codes align with `attribution.preflight`'s `ATTRIBUTION_BWRAP_MISSING` / `ATTRIBUTION_BWRAP_UNUSABLE`.
- New hosts get `bubblewrap` at creation from `deploy/cloud-init.yaml`; Ubuntu 24.04 still needs one Provision `install` after creation for the AppArmor profile. `bootstrap-server.sh` remains the source of truth for the base package list.
- The preflight in `release.sh` stays as the gate; the Deploy failure summary maps error codes to the Provision entry and runbook. Deploy's sudoers are unchanged.

## Alternatives considered

- **Give deploy apt rights**: apt maintainer scripts and hooks run as root, which is equivalent to giving the pipeline root, and routine releases do not need package installation. Rejected.
- **Install on demand inside `release.sh`**: every release could trigger a root operation, weakening the fail-closed preflight and requiring Deploy to carry root credentials. Rejected.
- **Ask an administrator to rerun `bootstrap-server.sh` every time**: that script touches users, MySQL, nginx, and systemd, which is far too broad as a single-package remedy and needs a human. Rejected.
- **Alibaba Cloud Cloud Assistant/OOS with a RAM role**: it removes the host SSH key but needs extra cloud API credentials, roles, and call chains; this iteration uses a dedicated root SSH key, and the same entry can switch implementations later. Deferred.
- **Add a `provision` job plus `needs` to the Deploy workflow**: that would carry root on every release and enlarge the blast radius; it stays an optional wiring, with the standalone entry as the default. Rejected as the default.

## Consequences

- Existing hosts need a one-time root authorization: add the dedicated public key to `authorized_keys` and store the private key in the `production` environment's `PROVISION_SSH_KEY`; the workflow then runs it, the key can rotate, and logs contain no credentials.
- The `production` environment currently has no required reviewers, and GitHub exposes environment secrets to every job in the same environment; Deploy also declares that environment but never references the root key in code. Truly scoping it to one workflow needs a separate environment or required reviewers; this account lacks the admin rights to create an environment, so this is a known limitation.
- `--check` exits non-zero with `ATTRIBUTION_BWRAP_MISSING` when the package is absent, so the check itself can make the workflow red; that is the intended observable signal, and the same command turns green after installation. The AppArmor profile is installed by Provision and persists in `/etc/apparmor.d`, where apparmor.service reloads it on boot.
- New system prerequisites follow the same pattern: the script offers a read-only check and an idempotent install, CI verifies the contract on a clean host (see #552), and Deploy stays fail-closed.
- This iteration introduces no cloud API, Packer, or Ansible; revisit when multi-host or compliance needs appear.
