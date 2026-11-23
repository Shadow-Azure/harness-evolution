# Fail explicitly instead of degrading clusters when a real AI provider is configured

English | [中文](bugfix-ai-agent-real-mode-no-degrade.md)

```yaml flow
kind: issue
id: bugfix-26
milestone: bugfix
depends:
  - bugfix-15
  - bugfix-17
  - bugfix-19
  - bugfix-23
priority: P2
status: done
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/app/config.py
  - apps/api/app/main.py
  - apps/api/tests/**
  - tests/e2e/**
  - packages/contracts/**
  - apps/web/**
  - deploy/**
  - .github/workflows/**
  - scripts/doc-budgets.manifest.json
  - docs/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 521
  url: https://github.com/Shadow-Azure/harness-evolution/issues/521
```

## Background

In production run `01M834EBAY3C9BB3TM8V85VHQN` (2026-11-23 10:40, target `codespec-subagent-driven-development`) the user still saw cluster confidence `0.82` and severity `10.0` and suspected that clustering and confidence were still stub code. The investigation showed that the real provider is wired in, but all three real calls failed and the existing design silently degraded to deterministic fallbacks while the UI still showed "completed · self-evolution effective". The user's requirement is explicit: **when the configuration says not to use fake, do not degrade**. The user then asked why `deploy` and the runtime user are two accounts, whether that is normal, and whether the root cause can be fixed entirely through the deploy pipeline.

### Problem: deploy and harness are two users

- `deploy` is the SSH/release account: it owns `/opt/harness`, writes releases, injects `.env`, and restarts the service. M15 also installs Claude Code as this user under `/home/deploy/.local/bin/claude` and `/home/deploy/.claude` (directory 0700, settings/api-key 0600/0700).
- `harness` is the service account: `deploy/harness-api.service` uses `User=harness`; bootstrap creates it with `useradd --system --no-create-home --shell /usr/sbin/nologin`. It has no home and no access to deploy's directory. systemd starts the API worker, the clustering AI calls, and git workspaces as this user.
- The provider default is `~/.local/bin/claude`; `Path(configured).expanduser()` expands to `/home/harness/.local/bin/claude` under harness (absent). `ClaudeCodeProvider._settings_file()` always reads `Path.home()/".claude"/settings.json`, i.e. `/home/harness/.claude/settings.json` (also absent; it never looks at deploy's home).
- As a result all three real calls fail during spawn (`could not start`, 7–8 ms, 0 tokens); `cluster_llm` folds the failure into the `0.82`/`10.0` fallbacks; the page shows no degradation and still says "self-evolution effective". That is why the user sees "stub code".

### Root cause

1. **Asset ownership mismatch (direct cause)**: Claude Code is a user-level tool of `deploy`, not a service-level asset usable by `harness`. M15 installs and configures it in deploy's home; the provider only looks at the service user's home; there is no shared path, group, ACL, or configurable settings path between them.
2. **Ownership gap (structural cause)**: M15 explicitly lists "do not wire Claude Code into harness-api" as a non-goal; #492 (bugfix-17) only covers the provider subclass under `apps/api`; #499 only injects the three keys into `.env`; `docs/deployment.md` defers "stable path and shared settings" to bugfix-17/M15, but neither contains it. No issue truly owns "let harness execute the CLI and read settings/credentials".
3. **Defaults and systemd environment (amplifier)**: `HE_AI_AGENT_CLAUDE_BIN` defaults to `~/.local/bin/claude`; there is no `HE_AI_AGENT_CLAUDE_SETTINGS`; system services do not inherit a login shell's HOME/PATH, so `~/.local/bin` and deploy's bin are not on PATH; settings/api-key live in a 0700 directory and 0600 files owned by deploy.
4. **Silent degradation (outcome cause)**: `cluster_llm` catches every review/score/severity exception and returns fallbacks; `prepare` still persists clusters and emits `clusters_created`; the API/UI do not expose `degraded`; the run verdict is derived from the fake evaluation's 85 > 80. A real failure is disguised as a normal result.
5. **The two-user split itself is not wrong**: separating the deploy account from the runtime account is standard least privilege. Running the service as `deploy` would give a compromised service deploy's home, SSH deployment credentials, and release-write access. The bug is that a user-level CLI/config was not promoted to a service-level asset, and that failures are swallowed.

### Analysis process

1. Read the production run events: seq 6/8/10 are the `cluster.review`, `cluster.score`, and `severity.score` `ai_agent_call` events; all use `provider=claude-code`, all have `outcome=error`, and each takes 7–8 ms with `model=unknown`, `inputTokens=0`, `outputTokens=0`, and `costUsd=0`. Seq 7/9/11 are the matching `degraded` events with the same reason: `AgentProviderError: claude-code analysis call could not start`. Seq 12 still records `algorithm=hybrid-lexical-llm-v1` but lists `degraded=[cluster.review, cluster.score, severity.score]`.
2. Read the deploy logs: the two most recent successful Deploy runs (`45101610757` / `45099843286`) show `claude-code 2.1.323` installed and `settings: /home/***/.claude/settings.json`, but also `AI Agent Secret: 0/3 written, the rest removed`. `CLAUDE_CODE_MODEL`, `CLAUDE_CODE_API_KEY`, and `CLAUDE_CODE_BASE_URL` are configured.
3. Read the configuration and deployment topology: `Settings` defaults to `ai_agent_provider=claude-code` and `ai_agent_claude_bin=~/.local/bin/claude`; `deploy/harness-api.service` uses `User=harness`; bootstrap creates the user with `useradd --system --no-create-home`; the M15 installer writes `~/.claude` as deploy and chmods it 0700; the unit sets no `Environment=HOME` or extra PATH.
4. Read the clustering and provider code: `prepare.py` takes the lexical path when `agent is None` and otherwise calls `_enhance_clusters`; `cluster_llm.py` falls back to lexical drafts when `cluster.review` fails, to `TYPE_CONFIDENCE[type]` when `cluster.score` fails, and to `cluster_severity()` when `severity.score` fails; `claude_code.py` maps the `OSError` from `create_subprocess_exec` to `could not start`; `_settings_file()` is hard-coded to `Path.home()/.claude` with no configuration knob.
5. Read the page and API: the `/steps/clusters` DTO has no `algorithm` or `degraded` field; a browser capture shows 82% / 10.0 and "✓ completed · self-evolution effective" with no AI degradation notice.
6. Researched how deploy and runtime user separation is handled elsewhere: a dedicated non-login service account is the recommended pattern ([SSD Nodes: Run services as an unprivileged user](https://www.ssdnodes.com/learn/least-privilege-users-vps)); systemd offers `LoadCredential=`, `DynamicUser=`, `StateDirectory=`, and `ConfigurationDirectory=` ([systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)); system services have HOME/PATH pitfalls ([Huawei Cloud: systemd service HOME is empty](https://bbs.huaweicloud.com/blogs/522224)).
7. Read the Claude Code environment documentation: `CLAUDE_CONFIG_DIR` overrides `~/.claude` for settings/session/plugins ([Claude Code env-vars](https://code.claude.com/docs/en/env-vars)); `--no-session-persistence` is already used by analyze; #488 decided edits are single-shot and a rejection ends the turn, `EditRequest` has no session_id, yet `_edit_argv` still keeps the session and `EditResult.session_id` has no consumer. That is a leftover from the original resume loop in #492.
8. Compared options: (1) a service-owned HOME (`Environment=HOME` + `StateDirectory`) works but creating `/home/harness`/chown needs root or bootstrap; (2) a shared config directory plus group/ACL plus a configurable settings path works but depends on `setfacl` or a one-time root initialization; (3) systemd `LoadCredential` is the safest but needs root to edit the unit and place credentials, so it is not pipeline-only; (4) running the service as deploy is simplest but violates least privilege and is not recommended.

### Conclusion

- The code is not stub code: `provider=claude-code` and `algorithm=hybrid-lexical-llm-v1`, and the real subclass was invoked three times.
- The direct cause is that the CLI/settings are invisible to harness; the structural cause is that a user-level asset was never promoted to a service-level asset and no issue owned it; the outcome cause is silent degradation plus no UI exposure.
- The two-user split is normal and should stay. The bug is treating the CLI as deploy's private file.
- A Secret-only fix is insufficient; documentation-only is insufficient. The root fix must make harness able to execute a stable CLI path, read settings/credentials, and fail explicitly in real mode without persisting fallbacks.
- **A pipeline-only fix is possible**: `CLAUDE_CONFIG_DIR` + shared settings (0644, no secret) + `ANTHROPIC_API_KEY` (reuse the existing `CLAUDE_CODE_API_KEY`, write it into the 0600 `.env`) + a stable `current` symlink; add `--no-session-persistence` to edit (#488 is already single-shot), so ACLs/root are mostly unnecessary. If Claude Code 2.1.323's `--bare` does not honor `CLAUDE_CONFIG_DIR`, add a small `HE_AI_AGENT_CLAUDE_SETTINGS` fallback, still deployed by the pipeline.

### Solution requirements

- **No fake**: when `AI_AGENT_PROVIDER` is not `fake` (including the default `claude-code`), a clustering AI failure must fail the run explicitly; no fallback confidence/severity, no "self-evolution effective".
- **Fix the root cause**: do not stop at a Secret, documentation, or a warning; make the CLI/settings usable by harness and correct the failure semantics.
- **Prefer the pipeline**: complete the work from the Deploy pipeline rather than manual server edits. If root/manual steps are unavoidable, state the minimal steps, the reason, and the rollback.
- **Verifiable**: a real run has `ai_agent_call` with `outcome=ok`, tokens > 0, a non-unknown model, and no `clusters_created.payload.degraded`; the page no longer shows "self-evolution effective" for a failed result.
- **Keep security boundaries**: keep the deploy/harness split and least privilege; do not use 0777, do not run the service as deploy, and do not put secrets into settings or the repository.

### Recommended root fix

1. **Keep both users**: deploy only releases/restarts; harness only runs the service; do not share a home or downgrade the service to deploy.
2. **Make Claude Code a service-level asset (pipeline-only)**:
   - `deploy/install-claude-code.py` creates a stable `current` symlink next to the versioned directory and writes a shared `settings.json` under `/opt/harness/shared/claude-code/config` (0644, no `apiKeyHelper` or secret; keep model, `ANTHROPIC_BASE_URL`, model aliases, MiniMax settings).
   - Deploy injects `CLAUDE_CONFIG_DIR=/opt/harness/shared/claude-code/config`, `ANTHROPIC_API_KEY` (value reused from `CLAUDE_CODE_API_KEY` over the existing base64/stdin channel), and `HE_AI_AGENT_CLAUDE_BIN=/opt/harness/shared/claude-code/current/usr/bin/claude` into the 0600 `/opt/harness/shared/.env`; no new Secret.
   - Claude Code reads settings from `CLAUDE_CONFIG_DIR` and the key from the environment; harness does not need deploy's home or a chown.
   - Add `--no-session-persistence` to `_edit_argv` (#488 is single-shot) to remove the leftover session write; the shared config can then stay read-only and no ACL is needed (if the CLI still writes other caches, confirm with one smoke test and then use `setfacl -m u:harness:rwx` or a writable state subdirectory).
   - Run one real `claude -p`/run smoke after deploy. If `--bare` does not honor `CLAUDE_CONFIG_DIR`, add a `HE_AI_AGENT_CLAUDE_SETTINGS` setting (explicit in `_settings_file()`) as the fallback; still pipeline-deployed.
3. **No degradation in real mode (this issue's core)**: add `HE_AI_AGENT_FAILURE_POLICY=strict|degrade`, defaulting by provider (`fake` → `degrade`, others → `strict`); in strict mode `cluster_llm` raises `ClusterAIFailure`, `prepare` persists no fallback clusters, and the engine marks the run failed/blocked with a diagnosable error. Degrade is explicit only.
4. **Observability**: `/steps/clusters` exposes algorithm/failurePolicy/degraded/failure reason; the UI stops showing "self-evolution effective" for failures; the Deploy preflight checks that `current` is executable and settings are readable, and aborts before switching `current`.
5. **Alternatives (root/one-time bootstrap)**: (3) `LoadCredential` (safest, but root must edit the unit and place credentials); (1) a service-owned HOME (root must create `/home/harness` or chown); (2) the ACL variant (unavailable when `setfacl` is absent). These are not preferred because they fail the pipeline-only requirement.

## Goals

- Define "real mode": when `AI_AGENT_PROVIDER` is not `fake` (including the default `claude-code`), a failure of any clustering AI call must fail the run at the clustering stage; the run must not persist fallback confidence/severity and must not be marked valid or accepted.
- Keep degradation, but only for `fake` or an explicit allow-degrade configuration: `HE_AI_AGENT_FAILURE_POLICY=strict|degrade`, defaulting to `strict` for real providers and `degrade` for `fake`. Degradation must be visible in the API/UI and must not masquerade as a normal result.
- Make failure diagnosable: keep `ai_agent_call` fields (task/provider/model/tokens/cost/latency/outcome) and record a sanitized failure category and stage; the run error/blocked message must point to the CLI path, settings readability, or authentication.
- Stop showing "self-evolution effective" for degraded or failed results: the clustering step must show the failure reason and the run verdict must follow; fake evaluation scores must not be treated as evidence that the real model participated.
- Pipeline-only deployment prerequisite: `CLAUDE_CONFIG_DIR` + shared settings + environment key + stable `current`; `HE_AI_AGENT_CLAUDE_BIN` points to a harness-executable absolute path; edit uses `--no-session-persistence`; Deploy runs a preflight before switching `current`.

## Design authority

- [07 §5.5.2](../../../plans/fullstack-design/07-backend-implementation.md): the three-layer clustering review/scoring tasks and the three degradation paths; this issue changes the "is degradation allowed in real mode" contract and adds the deployment prerequisite.
- [07 §5.5.1](../../../plans/fullstack-design/07-backend-implementation.md): the AI Agent provider parent contract and `AI_AGENT_PROVIDER` selection; the strict/degrade policy belongs at this seam rather than in business branches.
- [06 §5.3](../../../plans/fullstack-design/06-database-design.md): the persisted `confidence`/`severity`/`rank` contract; strict failures must not write fallback values and pollute the zero-migration columns.
- [2026-11-22 real-AI design note](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/feature/2026-11-22-evolution-real-ai-design.md): the original "worst case equals today's behavior" degradation trade-off; this issue records that the trade-off no longer holds in real mode and adds the deploy/harness user-boundary root fix.
- External references: [systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html) (`LoadCredential`/`DynamicUser`/`StateDirectory`/`ConfigurationDirectory`), [SSD Nodes dedicated service account](https://www.ssdnodes.com/learn/least-privilege-users-vps), [systemd HOME/PATH pitfalls](https://bbs.huaweicloud.com/blogs/522224), [Claude Code env-vars / CLAUDE_CONFIG_DIR](https://code.claude.com/docs/en/env-vars).

## Implementation

- **Configuration and policy resolution**: add `ai_agent_failure_policy: Literal["strict", "degrade"]` to `Settings` (environment key `HE_AI_AGENT_FAILURE_POLICY`), defaulting by provider (`fake` → `degrade`, anything else → `strict`); unknown values fail startup; update `deploy/env.production.example` and `docs/deployment.md`.
- **Propagate clustering failures**: in strict mode, `cluster_llm.enhance_clusters` must raise a `ClusterAIFailure` carrying the task and a sanitized reason instead of catching and returning fallbacks; `prepare._enhance_clusters` lets it propagate; `prepare` must not call `replace_prepared_clusters` to persist fallback clusters and must not emit a successful `clusters_created`.
- **Run/stage semantics**: the engine maps the clustering failure to `failed` (or the existing `blocked` state when the failure needs a human or retry), records the stage error, and keeps the already-recorded `ai_agent_call` events. Do not use the misleading `degraded` success wording. Retries continue to use the existing run retry, with no new turn-level loop.
- **Pipeline-only deployment prerequisite**: `deploy/install-claude-code.py` writes the shared `settings.json` (0644, no secret) and the `current` symlink; `deploy.yml` injects `CLAUDE_CONFIG_DIR`, `ANTHROPIC_API_KEY` (reused from `CLAUDE_CODE_API_KEY`), and `HE_AI_AGENT_CLAUDE_BIN`; `_edit_argv` adds `--no-session-persistence`; if needed, add `HE_AI_AGENT_CLAUDE_SETTINGS` and make `_settings_file()` use the explicit path.
- **API/UI**: `/steps/clusters` gains algorithm/failurePolicy/degraded/failure reason; regenerate `packages/contracts` and generated types; the page no longer shows "self-evolution effective" for failures.
- **Tests**: in strict mode any task failure → run fails and no fallback clusters are persisted; fake/degrade mode keeps the existing fallback; CLI ENOENT/EACCES/non-zero exit/timeout map to diagnosable failures; the deployment preflight failure branch is asserted; `CLAUDE_CONFIG_DIR`/shared settings/`--no-session-persistence` have unit or smoke coverage.

## Implementation steps

1. Define the strict/degrade configuration and default derivation; add Settings validation, env template, deploy injection, and unit tests.
2. Rework failure propagation and run state in `cluster_llm`/`prepare`/engine; strict failures persist no fallback values, while degrade remains available but explicitly visible.
3. Implement the pipeline-only deployment prerequisite: shared settings + `current` symlink + `CLAUDE_CONFIG_DIR`/`ANTHROPIC_API_KEY`/`HE_AI_AGENT_CLAUDE_BIN` injection; add `--no-session-persistence` to `_edit_argv`.
4. Extend the API/UI failure and degradation display; update contracts and regenerate types.
5. After deploy, verify one real run with `outcome=ok`, tokens > 0, and no degradation. If `CLAUDE_CONFIG_DIR` is not honored, add the `HE_AI_AGENT_CLAUDE_SETTINGS` fallback and retry.
6. Add strict/degrade/deployment tests and documentation, update the Agent Note, and run the gates.

## Dependencies and boundary

- Depends on bugfix-15 (provider skeleton and Settings), bugfix-17 (real Claude Code subclass), bugfix-19 (three-layer clustering and existing degradation), and bugfix-23 (three-key Secret injection).
- Delivery boundary: this issue owns the "no silent degradation in real mode" contract, API/UI visibility, and the pipeline-only deployment prerequisite (shared settings/current/env key/no-session edit). It does not change patch generation semantics (agent-edit), the evaluation gateway, or the turn lifecycle.
- Production Secret values (model API key, CLI absolute path) never enter the repository; documentation only names keys, semantics, and verification commands. `ANTHROPIC_API_KEY` is injected by Deploy from the existing `CLAUDE_CODE_API_KEY`; no new Secret is added.

## Verification

```sh
pnpm test:api -- tests/test_clustering_three_layers.py
pnpm test:api -- tests/test_ai_agent_claude_code.py
pnpm test:gates
pnpm verify:flow
```

- Strict case: a mock provider fails `cluster.review`/`cluster.score`/`severity.score` in turn; assert the run fails at the clustering stage, no fallback clusters are persisted, no successful `clusters_created` is emitted, and the error contains the task and a sanitized reason.
- Degrade case: provider=fake or explicit `degrade`; assert the existing lexical/constant/formula fallbacks and events are unchanged.
- Deployment case: preflight fails the release when harness cannot execute the CLI or read settings; `CLAUDE_CONFIG_DIR`/shared settings/`--no-session-persistence` have argv/config assertions; it passes when configured correctly.
- Production case: a real run's `ai_agent_call` has `outcome=ok`, tokens > 0, and a non-unknown model; `clusters_created.payload.degraded` is absent.

## Acceptance

- With `AI_AGENT_PROVIDER=claude-code` (including the default) and any clustering AI call failure, the run does not become "effective/accepted"; the clustering stage fails explicitly, no fallback confidence/severity clusters are persisted, the page does not show "self-evolution effective", and the error identifies the CLI path/settings/authentication.
- With `AI_AGENT_PROVIDER=fake` or explicit `HE_AI_AGENT_FAILURE_POLICY=degrade`, the existing degradation behavior and tests are unchanged.
- After the pipeline-only configuration, a real run's `ai_agent_call` has `outcome=ok`, tokens > 0, and a non-unknown model; `clusters_created.payload.degraded` is absent and confidence is no longer exactly the category constant; no manual SSH/root step is needed.
- Deploy fails before switching `current` when the CLI/settings are unavailable, so bad configuration is not shipped; `current`/shared settings/environment key paths are stable and CLI upgrades do not break the Secret.
- Unit tests, contract checks, `test:gates`, and `verify:flow` are green.

## Gates and CI

- api-static / unit-tests-api / docs-flow; add `pnpm contract:check` when contracts change; add deploy tests and `pnpm test:gates` when deployment changes.
- Commit and PR titles include `(#N)`.

## Non-goals

- Do not keep a "silent degradation + normal result" compatibility path in real mode; do not treat `degraded` as a success signal.
- Do not change the deterministic behavior of the `fake` provider, and do not remove the `degrade` capability (it is the explicit offline/test choice).
- Do not run the service as deploy, do not use 0777, do not put secrets into settings or the repository, and do not use a broader root/sudo grant as the default.
- Do not implement the agent-edit Settings enum expansion, the switch from fake to real evaluation, or turn-level automatic retries in this issue.
