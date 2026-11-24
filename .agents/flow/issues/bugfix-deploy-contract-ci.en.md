# CI gate: deployment provisioning contract on pull requests

English | [中文](bugfix-deploy-contract-ci.md)

```yaml flow
kind: issue
id: bugfix-45
milestone: bugfix
depends: [bugfix-33]
priority: P2
status: ready
scope:
  - deploy/**
  - apps/api/tests/deploy/**
  - .github/workflows/ci.yml
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr: []
github:
  number: 552
  url: https://github.com/Shadow-Azure/harness-evolution/issues/552
```

## Background

- PR #543 added `attribution.preflight` to the attribution runtime: on Linux, a missing `bubblewrap` returns `ATTRIBUTION_BWRAP_MISSING` and fails the release before switching `current`. That PR's CI was fully green and merged, but the next Deploy failed at preflight on the production host while the previous release kept serving.
- The cause is that PR CI only verified code behaviour, not the deployment provisioning contract; Deploy is triggered by `workflow_run` after merge, so the first real-environment check happened after merge. #553 provides the idempotent `deploy/provision-bubblewrap.sh` and the Provision entry, but the contract is not part of the required PR checks.
- This issue adds only the CI gate: a PR that adds a deployment runtime prerequisite without an executable provisioning path must fail before merge instead of waiting for production Deploy.

## Goals

- Run `deploy-contract` on a clean Ubuntu container: verify the negative case without `bwrap`, run the real provision script, then run the `bwrap` namespace probe and `attribution.preflight` as the service account.
- Keep a single source of truth for provisioning packages: `deploy/attribution-runtime-prerequisites.list`. Bootstrap reads it, cloud-init and the Provision path stay consistent with it, and CI fails when they drift.
- Statically assert that `deploy/release.sh` calls preflight before switching `current`, so later changes cannot move the order.
- Add `deploy-contract` to `ci-ok.needs`; branch protection keeps `ci-ok` as the required check.
- Keep deploy unprivileged: no automatic package installation, retries, or skipped/weakened preflight.

## Design authority

- [01 §6 Deployment shape and scale-out path](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/01-architecture.md): single ECS, release/rollback, and deployment boundaries.
- [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml): PR triggers and the `ci-ok` aggregate.
- [`.github/workflows/deploy.yml`](../../../.github/workflows/deploy.yml): post-merge release via `workflow_run`.
- [`deploy/release.sh`](../../../deploy/release.sh): preflight runs before switching `current`.
- [`deploy/provision-bubblewrap.sh`](../../../deploy/provision-bubblewrap.sh): the install/verify script shared by Provision and CI.
- [#552](https://github.com/Shadow-Azure/harness-evolution/issues/552): root-cause analysis of the missing gate.

## Implementation

- `deploy/attribution-runtime-prerequisites.list`: OS prerequisites for the attribution runtime (currently `bubblewrap`), the common source for bootstrap and cloud-init.
- `deploy/bootstrap-server.sh`: install base packages by reading the list; a missing list fails instead of being skipped silently.
- `deploy/cloud-init.yaml`: keep installation at machine creation; `deploy-contract` asserts every listed package appears in cloud-init `packages`.
- `apps/api/tests/deploy/test_provisioning_contract.py`: static contract tests for the package list, bootstrap/cloud-init/Provision consistency, `release.sh` preflight order, CI job wiring, and `ci-ok.needs`.
- `apps/api/tests/deploy/verify_provisioning_contract.sh`: clean-host runtime contract. Without `bwrap`, `--check` exits 10 and prints `ATTRIBUTION_BWRAP_MISSING`; after creating the `harness` account, `--install` must reach `state=ready`, `bwrap --version` must work, and the service-account namespace probe must exit 0; finally run the real preflight as the service account and assert `ready=True`.
- `.github/workflows/ci.yml`: add a `deploy-contract` job (`ubuntu:24.04` container, minimal dependencies, static tests plus the clean-host contract) and add it to `ci-ok.needs`.
- Docs: add the required check, the provisioning contract, and the order for adding a deployment prerequisite to the deployment docs; add gate troubleshooting to the deployment playbook.

## Implementation steps

1. Add the runtime prerequisite list, make bootstrap read it, and mirror it in cloud-init.
2. Write the static contract tests and reproduce "removing the provisioning path turns the gate red" locally.
3. Write the clean-host runtime contract and exercise missing-package/install/probe/preflight on Ubuntu 24.04.
4. Add the `deploy-contract` job in `ci.yml` and include it in `ci-ok`.
5. Update both sides of the deployment docs and the deployment playbook.
6. Push a PR and verify CI; removing cloud-init or the Provision path must fail `deploy-contract`, and restoring it must pass.

## Dependencies and boundary

- Dependencies: bugfix-33 (`deploy/provision-bubblewrap.sh` and the Provision entry); this issue does not reimplement the installer.
- Delivery boundary: the PR CI job, static/runtime contract tests, package-list convergence, release-order assertion, docs, and flow.
- Non-goals: no automatic installation/retries/skipped preflight; no app-code or attribution-sandbox changes; no apt for deploy; no change to Deploy triggering.

## Verification

```sh
apps/api/.venv/bin/python -m pytest apps/api/tests/deploy/test_provisioning_contract.py -q
sudo bash apps/api/tests/deploy/verify_provisioning_contract.sh
pnpm verify:flow
pnpm test:gates
pnpm lint:docs
pnpm verify:docs
bash -n deploy/provision-bubblewrap.sh deploy/bootstrap-server.sh apps/api/tests/deploy/verify_provisioning_contract.sh
```

- On a clean container without `bwrap`, the negative case exits 10 and prints `ATTRIBUTION_BWRAP_MISSING`.
- After installation, `bwrap --version`, the service-account probe, and `python -m app.third_party_api.ai_agent.preflight` all succeed; preflight prints `ready=True`.
- Removing `bubblewrap` from cloud-init or bootstrap fails the static contract tests; restoring it passes.

## Acceptance criteria

- A PR that adds or changes a deployment runtime prerequisite without an executable provisioning path fails the `deploy-contract` required check.
- `deploy-contract` runs the negative case, the provision positive case, and the service-account preflight on a clean container without mocking `bwrap`.
- `ci-ok` includes `deploy-contract`, and branch protection still requires `ci-ok`.
- The package list has one source; bootstrap, cloud-init, and the Provision script agree.
- Deploy remains unprivileged, with no automatic installation, retries, or skipped preflight.
- Docs, flow, and gates are green.

## Gates and CI

- `deploy-contract`: run the runtime and static contract tests in a clean `ubuntu:24.04` container and add the job to `ci-ok.needs`.
- `pnpm verify:flow`, `pnpm test:gates`, `pnpm verify:flow-online`: flow and PR association.
- `pnpm lint:docs`, `pnpm verify:docs`: deployment docs and bilingual pairing.
- `bash -n` and shellcheck where available: deployment script syntax.

## Non-goals

- No golden image/Packer, MySQL split, or containerized deployment.
- No change to `ATTRIBUTION_BWRAP_*` error-code semantics or the attribution sandbox.
- No apt for the deploy user and no system-package installation in `release.sh`.
- No production credentials, Session content, or host addresses in the repository.
