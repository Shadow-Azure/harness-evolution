# Close the deployment provisioning loop: bubblewrap and a standalone Provision entry

English | [中文](bugfix-provision-bubblewrap.md)

```yaml flow
kind: issue
id: bugfix-33
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - deploy/**
  - .github/workflows/provision.yml
  - .github/workflows/deploy.yml
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr: []
github:
  number: 553
  url: https://github.com/Shadow-Azure/harness-evolution/issues/553
```

## Background

- The local attribution Agent (`local-agent-skill-v1`) uses bubblewrap (`bwrap`) on Linux to sandbox each Claude Skill execution in a filesystem with read-only system paths and one writable attempt directory, protecting host `.env`, database credentials, and other cases/workspaces. The implementation lives in `apps/api/app/third_party_api/ai_agent/claude_skill.py`.
- PR #421 introduced attribution Skill execution and the bwrap sandbox and added `bubblewrap` to the base-package list in `deploy/bootstrap-server.sh`; PR #543 added `attribution.preflight`, which returns `ATTRIBUTION_BWRAP_MISSING` when bwrap is absent and fails the release before switching `current`, restoring `.env` first.
- The existing production host was initialized before bootstrap included `bubblewrap`, so the package is absent; the latest Deploy was therefore stopped by preflight while the previous release kept serving. New hosts get the package from bootstrap, but the existing host still needs a one-time root install.
- Deploy runs as the `deploy` user, and sudoers only allows `systemctl restart/start harness-api` and `harness-proxy`; an app deploy cannot run `apt-get`. Granting apt to deploy is effectively root (apt maintainer scripts and hooks run as root) and unacceptable.
- OS-package provisioning must become a controlled, auditable, repeatable pipeline capability; routine deploy stays unprivileged, and preflight remains the gate.

## Goals

- Existing hosts: a standalone Provision entry installs and verifies `bubblewrap` idempotently without manual SSH package installation.
- New hosts: cloud-init or Ansible installs it at machine creation; `bootstrap-server.sh` remains the package-list source of truth.
- Release: keep `attribution.preflight`; a missing bwrap still fails closed; deploy never gets apt.
- Observability: Provision logs, preflight error codes, a failure jump/runbook, and a clear distinction between `ATTRIBUTION_BWRAP_MISSING` and `ATTRIBUTION_BWRAP_UNUSABLE`.
- Security: a dedicated privileged account/cloud API plus production environment approval; a root-owned wrapper; keys never enter the repository or logs; rotatable and auditable.
- Optional: close the loop inside one Deploy workflow with a `provision` job plus `needs`; a standalone Provision entry is the default recommendation so routine releases never carry root.

## Design authority

- [01 §6 Deployment shape and scale-out path](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/01-architecture.md): single ECS, release/symlink/rollback, and deployment boundaries.
- [docs/deployment.en.md](../../../docs/deployment.en.md): single instance, the deploy user, release and rollback, and the bootstrap path.
- [PR #421](https://github.com/Shadow-Azure/harness-evolution/pull/421): attribution Skill execution and the bwrap sandbox; `bubblewrap` entered bootstrap.
- [PR #543](https://github.com/Shadow-Azure/harness-evolution/pull/543): `attribution.preflight`, stable error codes, and the pre-release check.
- [Attribution Agent executor Note](../../../.agents/notes/implemented/architecture/2026-11-17-attribution-agent-executor.en.md): per-invocation filesystem sandbox, trust boundary, and egress limits.
- [Attribution runtime incident record](../../../.agents/flow/issues/bugfix-attribution-runtime-silent-hang.en.md): the existing host lacked bwrap, and bindings were preserved and resumed.

## Implementation

- **Provision script**: add `deploy/provision-bubblewrap.sh` (run as root, idempotent). Check `command -v bwrap` first; when present run `bwrap --version` and a namespace probe; only when absent run `apt-get update && apt-get install -y bubblewrap`; finally run `bwrap --unshare-all --share-net --die-with-parent --ro-bind / / -- /bin/true` as `harness`; support `--check` and `--dry-run`; logs contain no credentials.
- **Provision workflow**: add `.github/workflows/provision.yml` with `workflow_dispatch` and `environment: production` (human approval), using a dedicated privileged account (root SSH key or a `provision` user plus a root-owned wrapper) or Alibaba Cloud Cloud Assistant/OOS with a RAM role; execute the script over SSH; emit a summary; exit non-zero on failure.
- **New-host provisioning**: add `deploy/cloud-init.yaml` (`packages: [bubblewrap]`) or an Ansible base role; document the new-host creation path; keep the bootstrap package list consistent.
- **Deploy wiring**: keep the preflight in `release.sh`; provide an optional `provision` job plus a `deploy needs: provision` example (not enabled by default), or document that Provision runs before Deploy; do not change deploy's sudoers.
- **Error UX**: map `ATTRIBUTION_BWRAP_MISSING` / `UNUSABLE` to the Provision workflow/runbook; have the Deploy summary give the next-step link.
- **Tests**: `bash -n` / shellcheck for the script; workflow syntax/actionlint; on temporary Ubuntu 22.04/24.04 hosts test missing-package install, the already-installed no-op, and a failing probe; regression-test Deploy preflight.
- **Docs**: add "Provision entry / new-host cloud-init / bubblewrap prerequisite" to `docs/deployment.md` / `.en.md`; update the runbook; keep the Chinese and English sides paired.

## Implementation steps

1. Add `deploy/provision-bubblewrap.sh` with a local dry-run/unit test; confirm `--check` returns a stable error code when the package is missing.
2. Add `provision.yml`, wired to `production` approval and the dedicated privileged credential; rehearse install/no-op/failing-probe in a temporary environment.
3. Add new-host cloud-init (or an Ansible base role) and make the package list in `bootstrap-server.sh` consistent with it.
4. Update `docs/deployment.*`, the runbook, and the Deploy failure hint; add the optional `provision` + `needs` example.
5. In production, run Provision once on the existing host, confirm `attribution.preflight` passes, then run the normal Deploy; do not retry the failed old release.
6. Run the gates and update the flow documents.

## Dependencies and boundary

- Dependencies: none; builds on the existing preflight and bootstrap package list from PRs #421/#543.
- Delivery boundary: the Provision script/workflow, the cloud-init/Ansible new-host path, Deploy documentation/optional wiring, related tests, and flow files.
- Non-goals: no golden image/Packer, no MySQL migration to RDS, no containers/K8s, no app-code changes, no changes to the attribution sandbox implementation, no apt for deploy, no automatic system-package installation from the API, and no production credentials or Session content in the repository.

## Verification

```sh
bash -n deploy/provision-bubblewrap.sh
shellcheck deploy/provision-bubblewrap.sh
pnpm verify:flow
pnpm test:gates
pnpm lint:docs
pnpm verify:docs
```

- On a temporary host without bwrap: `--check` exits non-zero and prints `ATTRIBUTION_BWRAP_MISSING`; after installation the probe exits 0.
- On a host that has it: the script is a no-op and does not repeat `apt-get update`; `bwrap --version` and the probe both succeed.
- When namespaces are unavailable: the probe fails, prints `ATTRIBUTION_BWRAP_UNUSABLE`, and the release does not switch.
- On temporary Ubuntu 22.04/24.04 hosts, run the script as root and then the same probe as `harness`; both should exit 0, and Deploy preflight should then pass.

## Acceptance

- Existing host: the approved Provision workflow installs/verifies bwrap; the following Deploy passes `attribution.preflight`; no manual SSH package installation is required.
- New host: after cloud-init or Ansible creation, `command -v bwrap` and the probe pass; Deploy preflight passes.
- The gate still works: after manually removing bwrap, Deploy still fails before switching `current` and the previous release keeps serving.
- Deploy's sudoers are unchanged and still lack apt/dpkg; Provision uses an independent privileged path.
- `ATTRIBUTION_BWRAP_MISSING` / `UNUSABLE` are distinguishable in logs and the runbook; Provision logs are auditable and contain no credentials.
- Documentation, workflow, scripts, and flow gates are all green; the Chinese and English docs are paired.

## Gates and CI

- `pnpm verify:flow`, `pnpm test:gates`: flow/dependency/body/state-machine checks.
- `pnpm lint:docs`, `pnpm verify:docs`: deployment docs and Chinese/English pairing.
- `bash -n`, shellcheck, actionlint (when available): static checks for scripts and workflows.
- In a temporary Ubuntu environment, exercise the provision install/no-op/failing-probe paths; regression-test Deploy preflight.

## Non-goals

- No complete immutable infrastructure/golden image and no MySQL split or containerization; open a separate issue when multi-host or compliance needs appear.
- Do not put `apt-get` into `release.sh` or the app deploy sudoers; do not use the root SSH key for routine Deploy.
- Do not change the mounts/isolation semantics of the attribution sandbox or the meaning of the `ATTRIBUTION_BWRAP_*` error codes.
- Do not write production credentials, Session content, private Feishu content, or host addresses into the repository.
