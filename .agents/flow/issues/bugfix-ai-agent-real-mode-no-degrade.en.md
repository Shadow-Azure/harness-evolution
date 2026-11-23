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
status: backlog
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/app/config.py
  - apps/api/tests/**
  - packages/contracts/**
  - apps/web/**
  - deploy/**
  - docs/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 521
  url: https://github.com/Shadow-Azure/harness-evolution/issues/521
```

## Background

In production run `01M834EBAY3C9BB3TM8V85VHQN` (2026-11-23 10:40, target `codespec-subagent-driven-development`) the user still saw cluster confidence `0.82` and severity `10.0` and suspected that clustering and confidence were still stub code. The investigation showed that the real provider is wired in, but all three real calls failed and the existing design silently degraded to deterministic fallbacks while the UI still showed "completed · self-evolution effective". The user's requirement is explicit: **when the configuration says not to use fake, do not degrade**.

### Analysis process

1. Read the production run events: seq 6/8/10 are the `cluster.review`, `cluster.score`, and `severity.score` `ai_agent_call` events; all use `provider=claude-code`, all have `outcome=error`, and each takes 7–8 ms with `model=unknown`, `inputTokens=0`, `outputTokens=0`, and `costUsd=0`. Seq 7/9/11 are the matching `degraded` events with the same reason: `AgentProviderError: claude-code analysis call could not start`. Seq 12 still records `algorithm=hybrid-lexical-llm-v1` but lists `degraded=[cluster.review, cluster.score, severity.score]`.
2. Read the deploy logs: the two most recent successful Deploy runs (`45101610757` / `45099843286`) show `claude-code 2.1.323` installed and `settings: /home/***/.claude/settings.json`, but also `AI Agent Secret: 0/3 written, the rest removed`. `CLAUDE_CODE_MODEL`, `CLAUDE_CODE_API_KEY`, and `CLAUDE_CODE_BASE_URL` are configured.
3. Read the configuration and deployment topology: `Settings` defaults to `ai_agent_provider=claude-code` and `ai_agent_claude_bin=~/.local/bin/claude`. The service runs as `harness`, which is created with `useradd --system --no-create-home`, so the default path expands to `/home/harness/.local/bin/claude` and does not exist. M15 installs the CLI and `~/.claude` under the `deploy` user, which `harness` cannot read. `claude_code.py` maps the `OSError` from `create_subprocess_exec` to `could not start`, so the 7–8 ms failures are spawn failures, not API-key authentication failures.
4. Read the clustering code: `prepare.py` takes the lexical path when `agent is None` and otherwise calls `_enhance_clusters`; `cluster_llm.py` falls back to lexical drafts when `cluster.review` fails, to `TYPE_CONFIDENCE[type]` when `cluster.score` fails, and to `cluster_severity()` when `severity.score` fails. All three paths only record a `degraded` event; they neither block the run nor change the `hybrid-lexical-llm-v1` identity.
5. Read the page and API: the `/steps/clusters` DTO has no `algorithm` or `degraded` field, so the page cannot show the degradation, and the run verdict is still derived from the fake evaluation's 85 > 80. The real-call failure is therefore masked by two layers of apparently normal output.

### Conclusion

- The code is not stub code: `provider=claude-code` and `algorithm=hybrid-lexical-llm-v1`, and the real subclass was invoked three times.
- The immediate cause is that the CLI is invisible to `harness`: `AI_AGENT_PROVIDER`, `HE_AI_AGENT_CLAUDE_BIN`, and `HE_PATCH_SOURCE_MODE` are not configured (0/3), so the service falls back to `~/.local/bin/claude`, which does not exist for harness. Even with an absolute path, the CLI settings and credentials remain in deploy's 0700 home, which harness cannot read.
- The structural cause is silent degradation: the current design collapses every real-call failure into deterministic fallbacks and records only a warning. That is appropriate for `fake`/offline mode, but not for "configured for real AI", because it disguises an outage as normal 0.82/10.0 output and the user cannot tell whether the model participated.
- Fixing only the Secret is insufficient: both "harness can execute the CLI" and "harness can read settings/credentials" must be solved, and real-mode failures must become explicit. Otherwise timeouts, authentication failures, and CLI upgrades will still silently fall back.

## Goals

- Define "real mode": when `AI_AGENT_PROVIDER` is not `fake` (including the default `claude-code`), a failure of any clustering AI call must fail the run at the clustering stage; the run must not persist fallback confidence/severity and must not be marked valid or accepted.
- Keep degradation, but only for `fake` or an explicit allow-degrade configuration. Add `HE_AI_AGENT_FAILURE_POLICY=strict|degrade` with `strict` as the default for real providers and `degrade` as the default for `fake`. Degradation must be visible in the API/UI and must not masquerade as a normal result.
- Make failure diagnosable: keep `ai_agent_call` fields (task/provider/model/tokens/cost/latency/outcome) and record a sanitized failure category and stage; the run error/blocked message must point to the CLI path, settings readability, or authentication.
- Stop showing "self-evolution effective" for degraded or failed results: the clustering step must show the failure reason and the run verdict must follow; fake evaluation scores must not be treated as evidence that the real model participated.
- Fix the deployment prerequisite: `HE_AI_AGENT_CLAUDE_BIN` must point to a stable absolute path that harness can execute; CLI settings/credentials must be readable by harness (or use environment-based authentication); Deploy must run a preflight as harness before switching `current`.

## Design authority

- [07 §5.5.2](../../../plans/fullstack-design/07-backend-implementation.md): the three-layer clustering review/scoring tasks and the three degradation paths; this issue changes the "is degradation allowed in real mode" contract.
- [07 §5.5.1](../../../plans/fullstack-design/07-backend-implementation.md): the AI Agent provider parent contract and `AI_AGENT_PROVIDER` selection; the strict/degrade policy belongs at this seam rather than in business branches.
- [06 §5.3](../../../plans/fullstack-design/06-database-design.md): the persisted `confidence`/`severity`/`rank` contract; strict failures must not write fallback values and pollute the zero-migration columns.
- [2026-11-22 real-AI design note](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/proposed/feature/2026-11-22-evolution-real-ai-design.md): the original "worst case equals today's behavior" degradation trade-off; this issue records that the trade-off no longer holds in real mode.

## Implementation

- **Configuration and policy resolution**: add `ai_agent_failure_policy: Literal["strict", "degrade"]` to `Settings` (environment key `HE_AI_AGENT_FAILURE_POLICY`), defaulting by provider (`fake` → `degrade`, anything else → `strict`); unknown values fail startup; update `deploy/env.production.example` and `docs/deployment.md`.
- **Propagate clustering failures**: in strict mode, `cluster_llm.enhance_clusters` must raise a `ClusterAIFailure` carrying the task and a sanitized reason instead of catching and returning fallbacks; `prepare._enhance_clusters` lets it propagate; `prepare` must not call `replace_prepared_clusters` to persist fallback clusters and must not emit a successful `clusters_created`.
- **Run/stage semantics**: the engine maps the clustering failure to `failed` (or the existing `blocked` state when the failure needs a human or retry), records the stage error, and keeps the already-recorded `ai_agent_call` events. Do not use the misleading `degraded` success wording. Retries continue to use the existing run retry, with no new turn-level loop.
- **API/UI**: `/steps/clusters` gains failure/degradation information (at least algorithm, failurePolicy, degraded/failure reason); the clustering step and run verdict no longer show "self-evolution effective" for failed results; regenerate `packages/contracts` and generated types.
- **Deployment prerequisite**: produce a stable `/opt/harness/shared/claude-code/current/usr/bin/claude` symlink; write settings/credentials to a harness-readable shared path (or support `ANTHROPIC_API_KEY`/`ANTHROPIC_BASE_URL` environment authentication); inject `HE_AI_AGENT_CLAUDE_BIN` (and optionally `HE_AI_AGENT_CLAUDE_SETTINGS`); before switching `current`, run `claude --version` and a settings-readability check as harness, and abort the release on failure instead of going live and degrading silently.
- **Tests**: in strict mode any task failure → run fails and no fallback clusters are persisted; fake/degrade mode keeps the existing fallback; CLI ENOENT/EACCES/non-zero exit/timeout map to diagnosable failures; the deployment preflight failure branch is asserted; API/UI failure states are covered.

## Implementation steps

1. Define the strict/degrade configuration and default derivation; add Settings validation, env template, deploy injection, and unit tests.
2. Rework failure propagation and run state in `cluster_llm`/`prepare`/engine; strict failures persist no fallback values, while degrade remains available but explicitly visible.
3. Extend the API/UI failure and degradation display, update contracts, and regenerate types.
4. Implement the deployment prerequisite: stable path, harness-readable settings/credentials, preflight, and abort on failure.
5. Add strict/degrade/deployment tests and documentation, update the Agent Note, and run the gates.
6. After production is configured with `AI_AGENT_PROVIDER`, `HE_AI_AGENT_CLAUDE_BIN`, and settings/credentials, verify one real run with `outcome=ok`, tokens > 0, and no degradation.

## Dependencies and boundary

- Depends on bugfix-15 (provider skeleton and Settings), bugfix-17 (real Claude Code subclass), bugfix-19 (three-layer clustering and existing degradation), and bugfix-23 (three-key Secret injection).
- Delivery boundary: this issue owns the "no silent degradation in real mode" contract, API/UI visibility, and the deployment prerequisite code/configuration. It does not change patch generation (agent-edit), the evaluation gateway, or the turn lifecycle.
- Production Secret values (model API key, CLI absolute path) never enter the repository; documentation only names keys, semantics, and verification commands.

## Verification

```sh
pnpm test:api -- tests/test_clustering_three_layers.py
pnpm test:api -- tests/test_ai_agent_claude_code.py
pnpm test:gates
pnpm verify:flow
```

- Strict case: a mock provider fails `cluster.review`/`cluster.score`/`severity.score` in turn; assert the run fails at the clustering stage, no fallback clusters are persisted, no successful `clusters_created` is emitted, and the error contains the task and a sanitized reason.
- Degrade case: provider=fake or explicit `degrade`; assert the existing lexical/constant/formula fallbacks and events are unchanged.
- Deployment case: preflight fails the release when harness cannot execute the CLI or read settings; it passes when configured correctly.

## Acceptance

- With `AI_AGENT_PROVIDER=claude-code` (including the default) and any clustering AI call failure, the run does not become "effective/accepted"; the clustering stage fails explicitly, no fallback confidence/severity clusters are persisted, the page does not show "self-evolution effective", and the error identifies the CLI path/settings/authentication.
- With `AI_AGENT_PROVIDER=fake` or explicit `HE_AI_AGENT_FAILURE_POLICY=degrade`, the existing degradation behavior and tests are unchanged.
- After production is configured per the fix, a real run's `ai_agent_call` has `outcome=ok`, tokens > 0, and a non-unknown model; `clusters_created.payload.degraded` is absent and confidence is no longer exactly the category constant.
- Deploy fails before switching `current` when the CLI/settings are unavailable, so bad configuration is not shipped.
- Unit tests, contract checks, `test:gates`, and `verify:flow` are green.

## Gates and CI

- api-static / unit-tests-api / docs-flow; add `pnpm contract:check` when contracts change; add deploy tests and `pnpm test:gates` when deployment changes.
- Commit and PR titles include `(#N)`.

## Non-goals

- Do not keep a "silent degradation + normal result" compatibility path in real mode; do not treat `degraded` as a success signal.
- Do not change the deterministic behavior of the `fake` provider, and do not remove the `degrade` capability (it is the explicit offline/test choice).
- Do not implement the `agent-edit` Settings enum expansion, the switch from fake to real evaluation, or turn-level automatic retries in this issue.
- Do not write production Secret values into the repository, documentation, or the issue; do not add a root workaround that bypasses harness permissions.
