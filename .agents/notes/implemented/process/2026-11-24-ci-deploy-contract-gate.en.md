# Agent Note: Verify the deployment provisioning contract in PR CI

Status: implemented

English | [中文](2026-11-24-ci-deploy-contract-gate.md)

## Problem

PR #543 added `attribution.preflight` to the attribution runtime: on Linux, a missing `bubblewrap` fails the release before switching `current`. That PR's CI was fully green and merged, and only the next Deploy exposed the missing package on the production host while the previous release kept serving. PR CI verified code behaviour but never ran the real "prerequisite missing → provisioning → service account usable" path; Deploy is triggered by `workflow_run` after merge, so the first real-environment check happened after merge. Unit tests can mock `bwrap`, but the mock is exactly what hid the root cause of this incident.

## Decision

Move the deployment provisioning contract into the required PR check, in two layers:

- **Static contract** (`apps/api/tests/deploy/test_provisioning_contract.py`, run by the regular API suite): `deploy/attribution-runtime-prerequisites.list` is the single list of attribution runtime OS prerequisites; bootstrap reads it, cloud-init mirrors it, and the Provision script installs the same package; the `release.sh` preflight must come before `ln -sfn current`; the `deploy-contract` job must be in `ci-ok.needs`. Any drift fails at PR time.
- **Clean-host runtime contract** (`apps/api/tests/deploy/verify_provisioning_contract.sh`, run by the `deploy-contract` job on an Ubuntu container): first remove any preinstalled `bwrap` and verify `--check` exits 10 with `ATTRIBUTION_BWRAP_MISSING`; then run the real `deploy/provision-bubblewrap.sh --install` and assert `state=ready`, `bwrap --version`, and a namespace probe as `harness`; finally run the candidate code's `attribution.preflight` as `harness` and assert `ready=True`. No mocks; CI and the Provision workflow share the same script.
- Add `deploy-contract` to `ci-ok.needs`; branch protection still needs only `ci-ok` as the required check, so adding or removing lanes does not change repository settings.

## Alternatives considered

- **Add more pytest mock branches only**: rejected. The incident's root cause was that mocks covered bwrap existence; more mocks cannot prove the host runs the real probe.
- **Run `apt-get` automatically inside Deploy or retry on failure**: rejected. Deploy stays unprivileged; automatic installation would bring root into routine releases, and retries would hide missing provisioning.
- **Depend on a self-hosted runner or an image with bwrap preinstalled**: rejected. A preinstalled bwrap makes the negative case untrustworthy; the gate must go red then green on a clean environment without the prerequisite.
- **Move preflight out of the release path into CI**: rejected. Preflight is a runtime safety net and must stay on the real release path; CI only moves the same contract earlier, it does not replace it.

## Consequences

- PR time grows by one lane (Python dependencies plus a real provision, expected to take a few minutes); in return, "new runtime prerequisite without a provisioning path" fails before merge.
- When the attribution runtime gains an OS prerequisite, change `deploy/attribution-runtime-prerequisites.list` first, then mirror it in cloud-init and the Provision path; the static contract names each missing place.
- A container cannot load a host AppArmor profile, so the runtime contract proves the package exists and the service account can use bwrap; the Ubuntu 24.04 AppArmor remediation remains covered by the Provision script and the deployment playbook.
- Branch protection must make `ci-ok` the required check (a one-time repository setting); adding only the job without changing protection can still let a PR bypass it.
