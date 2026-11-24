# Deploy restart kills the in-flight edit CLI: agent-edit is classified as a terminal cancellation and fails the evolution run

English | [中文](bugfix-deploy-unit-drift-edit-cancelled.md)

```yaml flow
kind: issue
id: bugfix-49
milestone: bugfix
depends:
  - bugfix-11
  - bugfix-45
priority: P2
status: ready
scope:
  - deploy/**
  - apps/api/tests/deploy/**
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr: []
github:
  number: 583
  url: https://github.com/Shadow-Azure/harness-evolution/issues/583
```

## Background

### Problem context

At 2026-11-24 16:55:06 (+08), production evolution run `01M86AXB7180YHS9XY6D67KEG0` (target `codespec-subagent-driven-development@openspec-cn-main-copy-ar-a7ec200-claude-core`, workspace `OpenSpec-cn_SWE-bench`) failed terminally during patch generation of turn 2 in step 6/7 "iteration":

- Run page: `http://8.149.232.63/workspaces/01M7KJ05ENF9784GPBDV544VB0/evolution/runs/01M86AXB7180YHS9XY6D67KEG0`
- Database: `status=failed`, `error_stage=patch`, `error_message=claude-code edit call was cancelled`, `error_at=2026-11-24 16:55:06`, `blocked_stage=NULL`, `retry_attempts=0`.
- Turns: turn 1 was accepted (candidate 85.0 vs baseline 80.0, final commit `c4d3262`); turn 2 is `failed` (started 16:41:32, finished 16:55:06, `patch=NULL`); turn 3 is still `pending`.

### What the user saw

The first turn's change and evaluation succeeded; the page then reported "patch generation failed" in step 6 with only `claude-code edit call was cancelled`. The run did not become `blocked` and the page exposes no retry action, so the remaining two clusters will never be processed. This is not a model refusal, permission denial, or evaluation failure: all three analyze calls and the first edit call in the same run succeeded with non-zero token and cost records.

At 2026-11-24 18:20 (+08), the production front end was checked with the admin account: the run page shows the "failed" badge and a red error bar with `patch`, `claude-code edit call was cancelled`, and `2026-11-24T16:55:06+08:00`; step 5 "clusters and severity" is done, step 6 "iteration" is not clickable, and there is no retry action; the execution log has 22 entries, the last two being `run_failed` at seq 21/22. This matches the API/DB `error_stage=patch`, `error_message`, and `error_at` exactly.

Durable events and job rows show an interruption in the same second as a deployment:

| Time (+08) | Fact |
|---|---|
| 16:31:44 | Run created, prepare starts |
| 16:32:41 | Three clusters created |
| 16:36:01 | Turn 1 `agent.edit` succeeds (`latencyMs=192147`, 86020 tokens, cost 1.2078755) |
| 16:36:06 | Candidate pushed, evaluation submitted |
| 16:41:17 | Evaluation completes: 80.0 → 85.0, `externalVerdict=accept` |
| 16:41:32 | Turn 1 accepted; turn 2 job `01M86BF9RNZN7KAMRA95P4Y055` (`evolution_advance`) starts |
| 16:54:00 | New release `6d11b30` lands under `/opt/harness/releases/` |
| 16:55:05 | `systemctl restart harness-api`: `Stopping harness-api.service`, process shutdown begins |
| 16:55:05 | The same job fails with `ConfigError: claude-code edit call was cancelled`; `cancel_requested=0` |
| 16:55:06 | Run becomes `failed`; turn 2 becomes `failed` |
| 16:55:07 | New process finishes startup |

Turn 2 ran for 814 seconds, well below `EDIT_TIMEOUT_SECONDS=1800`, so this is not a timeout; `cancel_requested=0`, so it is not a user cancellation. The failure coincides to the second with the deploy restart.

## Goals

- Stop routine releases from SIGTERMing the running Claude Code child, so a deploy interruption is no longer disguised as a terminal `claude-code edit call was cancelled` provider failure.
- Make `release.sh` own systemd unit installation: the unit in the repository/staging directory and the live `/etc/systemd/system/harness-api.service` must not drift silently; a drift fails the release and keeps the old service instead of restarting with the wrong kill semantics.
- Lock three properties with executable contract tests: `KillMode=mixed`, `TimeoutStopSec` greater than the drain window, and unit installation plus effective-value verification before restart.
- After the fix, an in-flight edit job during a release must end as `interrupted` through the application drain, not as a terminal provider failure after systemd kills the child with exit 143.

## Design authority

- [01 §6 Deployment shape and expansion path](../../../plans/fullstack-design/01-architecture.md): single ECS, release directory, rollback and release boundary.
- [docs/deployment.md](../../../docs/deployment.en.md): current release order, rollback, shutdown drain and `HE_JOB_DRAIN_TIMEOUT_SECONDS`.
- [bugfix-11 deploy restart interruption](../../../.agents/flow/issues/bugfix-deploy-interrupt-recovery.en.md): leases, heartbeats, drain and the origin of `KillMode=mixed` / `TimeoutStopSec`; this issue fixes the deployment-side installation contract it did not fulfill.
- [bugfix-45 deploy provisioning contract in CI](../../../.agents/flow/issues/bugfix-deploy-contract-ci.en.md): the existing pattern of static contract tests under `apps/api/tests/deploy/` and ordering assertions on `release.sh`.
- [systemd.kill](https://www.freedesktop.org/software/systemd/man/latest/systemd.kill.html): the default `KillMode=control-group` sends SIGTERM to every process in the cgroup; `mixed` signals only the main process first and SIGKILLs the rest after the timeout.
- [Claude Code provider cancellation classification](../../../apps/api/app/third_party_api/ai_agent/claude_code.py): `CANCELLED_EXIT_CODE=143` is classified as `cancelled` with `retryable=False`.

## Root cause analysis

### Conclusion

The direct cause is that **the production systemd unit is older than the repository**: `/etc/systemd/system/harness-api.service` is still the version installed on 2026-11-19 and lacks `KillMode=mixed` and `TimeoutStopSec=45`, both added by `#474`. The `release.sh` restart therefore used systemd's default `KillMode=control-group`: SIGTERM reached the Python main process and the `claude` child it had spawned. The child exited 143 (128+SIGTERM), `ClaudeCodeProvider._call()` normalized 143 to `cancelled` (`retryable=False`), and `_fail_patch_generation()` wrote the run as a terminal failure.

The deeper contract gap is that **a release only updates the `current` symlink and restarts; it never installs the unit**. `deploy/harness-api.service` and `/opt/harness/shared/config/harness-api.service` already contain the correct configuration (pushed by the pipeline at 16:53), but `release.sh` only runs `systemctl restart`; only a manual root rerun of `bootstrap-server.sh` copies the unit to `/etc`. Thus the shutdown protection from `#474` exists in the repository and in the staging directory but never took effect in production.

### Analysis

1. **Read the failure facts from the run detail**: `evolution_runs` has `error_stage=patch` and `error_message=claude-code edit call was cancelled`; `evolution_rounds` row 2 has `started_at=16:41:32`, `finished_at=16:55:06`, `patch=NULL`; `job_runs` row `01M86BF9RNZN7KAMRA95P4Y055` is also `failed` with the identical `error`, and `cancel_requested=0`. Manual cancellation is ruled out.
2. **Align the deployment timeline**: `journalctl -u harness-api` shows `Stopping harness-api.service` at 16:55:05, the same second as `job execution failed error_type='ConfigError'`; the new process starts at 16:55:07; release `6d11b30` has mtime 16:54. The traceback on event seq 22 still points at `/opt/harness/releases/9377dfd7.../api/...`, showing that the process handling this job started from the pre-deploy release; `current` only switched to `6d11b30` at 16:55. The failure is in the same second as `systemctl restart`, not a business timeout or external evaluation.
3. **Read the cancellation classification**: `AsyncioClaudeCliRunner` sets `cancelled=True` only for its own timeout or when the task is cancelled. This call ran 814 seconds, below 1800 seconds, and the handler itself was not cancelled (otherwise `_run()` would have taken the `CancelledError` branch and marked the job `interrupted`). The only remaining path is the child returning `143`, matched by `_is_cancelled()` via `CANCELLED_EXIT_CODE`.
4. **Confirm where 143 came from**: `systemctl show harness-api -p KillMode` returns `KillMode=control-group`; `/etc/systemd/system/harness-api.service` has mtime 2026-11-19 23:22; a diff against `/opt/harness/shared/config/harness-api.service` shows only `KillMode=mixed` and `TimeoutStopSec=45` plus the comment above them. `git log deploy/harness-api.service` shows those lines were added by `#474` on 2026-11-21, so the production unit has not been updated by any release since then.
5. **Confirm the deploy pipeline does not install the unit**: `deploy/release.sh` runs preflight → Alembic → switch `current` → `systemctl restart harness-api` → health check, with no `install` or `daemon-reload`. Only `deploy/bootstrap-server.sh` installs the unit, and that is a one-time root bootstrap; `deploy.yml` only invokes `release.sh`. The staged unit under `/opt/harness/shared/config/` is current, but `/etc/` is stale.
6. **Connect the failure chain**: at 16:55:05 systemd sends SIGTERM to the whole service cgroup → the `claude` child receives SIGTERM and exits 143 → `_call()` takes `_is_cancelled(result)` → `_cancelled_error("edit")` builds `retryable=False` `AgentProviderError` → `_handle_provider_failure()` calls `_fail_patch_generation()` because the error is not retryable → `ConfigError("claude-code edit call was cancelled")` → run `failed`. Because the handler was not cancelled, `JobRunner._run()` never reached its `interrupted` branch.
7. **Exclusions**: not the 1800-second timeout (814 seconds); not model or auth (three analyze calls and turn 1 edit all succeeded with non-zero tokens/cost in the same run); not user cancellation (`cancel_requested=0`); not Git/workspace (turn 1 candidate was pushed; turn 2 failed inside the edit call); not evaluation (turn 1 was already accepted).

### Why it looked like the AI edit was cancelled

`_cancelled_error()` reuses the same message and `retryable=False` for both "the runner's own timeout/cancellation" and "the child was SIGTERMed by an external supervisor". The real semantics here were "the service is deploying and systemd killed the child too", but the page could only show "the call was cancelled", making it look like a model or provider decision. This classification turns a recoverable deployment interruption into an unrecoverable provider failure and writes the run as terminally failed instead of `interrupted` for restart recovery.

## Recommended solution (single)

**Make the systemd unit part of the release contract: before restarting, `release.sh` installs `$SHARED/config/harness-api.service` through a narrowly scoped root helper, runs `daemon-reload`, and asserts that the effective configuration is `KillMode=mixed` with `TimeoutStopSec` greater than the drain window; if any step fails, the release aborts and the old service keeps running.**

This fixes the root cause directly: the production unit can no longer lag behind the repository, and systemd signals only the main process on restart instead of killing the `claude` child. The main process then runs the existing 25-second `JobRunner.close()` drain; the edit call is cancelled by the application itself, `ClaudeCliCancelled` takes the `_run()` `interrupted` branch and writes `job interrupted during shutdown`, and no 143 or `claude-code edit call was cancelled` terminal failure is produced.

Concrete implementation:

1. **Add a narrowly scoped unit installer** `deploy/install-harness-unit.sh`: it only accepts the fixed `$SHARED/config/harness-api.service`, verifies the file contains `KillMode=mixed` and a `TimeoutStopSec` greater than `HE_JOB_DRAIN_TIMEOUT_SECONDS + 10`, runs `install -m 0644` to `/etc/systemd/system/harness-api.service` and `systemctl daemon-reload`, then verifies the effective `KillMode=mixed` and `TimeoutStopSec` through `systemctl show`, exiting non-zero on mismatch.
2. **Install the helper and minimal sudo rights in bootstrap**: `deploy/bootstrap-server.sh` installs the helper at `/usr/local/sbin/harness-install-unit` and adds a sudoers rule that lets the deploy account run only that helper; it does not grant arbitrary `install` or `systemctl daemon-reload` rights.
3. **Call and verify in the release path**: `deploy/release.sh` invokes `sudo -n /usr/local/sbin/harness-install-unit` before switching `current`; if the helper fails, the symlink is not switched and the service is not restarted, so the old release keeps serving. After success, assert again that `systemctl show -p KillMode --value harness-api` is `mixed` and `TimeoutStopSec` is sufficient; otherwise fail the release.
4. **One-time repair of the current production host**: run the helper (or rerun bootstrap) as root on 8.149.232.63, confirm `systemctl show -p KillMode` changes from `control-group` to `mixed`. This repairs the incident; every subsequent release then enforces the invariant.
5. **Lock it with a contract test**: add `apps/api/tests/deploy/test_unit_install_contract.py` asserting that release calls the helper before restart, bootstrap installs the helper and sudoers, the unit contains `KillMode=mixed` and `TimeoutStopSec`, and the helper verifies effective values; wire it into the existing `deploy-contract` job.
6. **Synchronize documentation**: update `docs/deployment.md` and its English counterpart so the release order becomes "install/verify unit → migrate → switch → restart → probe", state that unit changes no longer depend on a manual bootstrap, and document that existing hosts need one root helper run.

> This issue only covers the unit installation contract and deployment verification; it does not change the provider's 143 classification. After the fix, systemd no longer delivers SIGTERM to the child in this deploy scenario, so the 143 path is not reached; keeping the current classification avoids treating a deliberate user cancellation as a recoverable interruption. If the project later needs to cover "an operator kills the child directly", that should be a separate issue for shutdown-aware interruption classification.

## Implementation

- `deploy/install-harness-unit.sh`: the narrowly scoped installer and effective-value verification.
- `deploy/bootstrap-server.sh`: install the helper and minimal sudoers.
- `deploy/release.sh`: install and verify the unit before restart; fail without switching or restarting.
- `apps/api/tests/deploy/test_unit_install_contract.py`: static contract tests for the above.
- `docs/deployment.md`, `docs/deployment.en.md`, `docs/deployment.i18n.yaml`: release order and upgrade notes.
- `.agents/notes/`: record the decision that "the unit is part of the release contract and cannot depend on a one-time root bootstrap".

## Implementation steps

1. Write the helper; on a test host, first prove it rejects a unit missing `KillMode=mixed`.
2. Install the helper and sudoers through bootstrap; confirm the deploy account can execute only the helper.
3. Change `release.sh` to install the unit before switching `current`, and add the effective-value assertions.
4. Add the static contract test; delete the helper call or `KillMode` from the unit and confirm the test goes red.
5. Update the bilingual deployment docs and add the Agent Note.
6. Run the helper once on production and confirm the effective values; then perform a normal release and confirm the staged and `/etc` units are identical.
7. During the next release window, start a long edit call; confirm the restart ends the job as `interrupted`, not `failed`, and no event contains `claude-code edit call was cancelled`.

## Dependencies and boundary

- Depends on `bugfix-11` (design of `KillMode=mixed` / `TimeoutStopSec`) and `bugfix-45` (`apps/api/tests/deploy/` contract tests and the `deploy-contract` job).
- Related but not implemented here: [#578](https://github.com/Shadow-Azure/harness-evolution/issues/578) (startup recovery for `interrupted` jobs written by graceful shutdown). This issue ensures the job becomes `interrupted` rather than `failed`; recovery is #578's responsibility.
- Repairing the production host requires one root run of the helper or bootstrap; every later release enforces the invariant automatically.
- Does not change the provider's 143 classification, `EDIT_TIMEOUT_SECONDS`, the drain window, model invocation, or evaluation logic.

## Verification

Static contract and flow:

```sh
pnpm verify:flow
pnpm verify:flow-online
apps/api/.venv/bin/python -m pytest apps/api/tests/deploy/test_unit_install_contract.py -q
pnpm test:gates
pnpm lint:docs
```

Read-only production check:

```sh
systemctl show harness-api -p KillMode -p TimeoutStopSec
# Before: KillMode=control-group, TimeoutStopSec=90 (default)
# After:  KillMode=mixed, TimeoutStopSec=45

diff -u /etc/systemd/system/harness-api.service /opt/harness/shared/config/harness-api.service
# After: no differences
```

Release-behavior check (test host):

```sh
# 1. Start an evolution edit call that spans a release window
# 2. Run deploy/release.sh while the edit is in flight
# 3. After restart, check run / job:
#    - job.status = interrupted, error = job cancelled during shutdown
#    - no run error_stage=patch / claude-code edit call was cancelled
#    - if #578 is merged, job_recovered appears and turn 2 continues
```

- Expected: if unit installation fails, the release exits before switching and the old process keeps serving; when the unit is correct, no child exits 143 during restart and the job takes the `interrupted` path.

## Acceptance criteria

- [ ] Production `systemctl show harness-api -p KillMode` is `mixed`, and the `/etc` unit matches `$SHARED/config` byte for byte.
- [ ] `release.sh` installs and verifies the unit before `systemctl restart`; a missing or invalid unit fails the release without switching `current`.
- [ ] The contract test fails for "release does not call the helper", "unit lacks `KillMode=mixed`", and "`TimeoutStopSec` does not exceed the drain window".
- [ ] An in-flight edit job during a release ends as `interrupted`, and the run's `error_message` is no longer `claude-code edit call was cancelled`.
- [ ] Bilingual deployment docs describe the unit installation step, and an Agent Note records the decision.
- [ ] No broad root rights are granted to the deploy account.

## Gates and CI

- `pnpm verify:flow`, `pnpm verify:flow-online`, `pnpm test:gates`
- `pnpm test:api -- tests/deploy/test_unit_install_contract.py`
- The existing `deploy-contract` CI job (`apps/api/tests/deploy` tests)
- `pnpm lint:docs`, `pnpm verify:docs`
- Documentation budget: after editing `docs/deployment.md`, run `pnpm record:i18n -- docs/deployment.md` and update the budget manifest; coverage must stay above 80%.

## Non-goals

- Do not change the provider's exit-143 cancellation classification; do not turn cancellation into a retry.
- Do not lengthen or shorten `HE_JOB_DRAIN_TIMEOUT_SECONDS` / `EDIT_TIMEOUT_SECONDS`.
- Do not implement #578's `interrupted` startup recovery; do not rerun this failed run.
- Do not freeze release windows or require operators to wait for a run to finish before deploying.
- Do not grant the deploy account arbitrary `install`, `systemctl`, or root-shell rights.
- Do not change models, prompts, patch generation, evaluation, or frontend presentation.
