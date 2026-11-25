# AI Agent Outbound Layer

English | [中文](ai-agent.md)

Self-evolution review, scoring and patch generation call models through one outbound layer; installation and model setup live in [claude-code.en.md](claude-code.en.md).

## Layering

- `apps/api/app/third_party_api/ai_agent/` is the single outbound seam: business services call only `build_agent_provider`, never import a vendor module, and never branch on a backend name.
- `AIAgentProvider` defines contracts only: `analyze` (structured analysis), `edit_workspace` (a submitted edit plan), and the optional skill faces `stage_skill`/`run_skill` (attribution follows the provider switch). A subclass declares its capability faces explicitly via `capabilities` (`analyze`/`edit`/`skill`); subclasses that never declared keep the `run_skill`-override derivation. `ProviderHealth.auth` (`ok`/`missing`/`unknown`) and the preflight capability line make credential state and binary usability enumerable.
- The factory selects a registered subclass by `AI_AGENT_PROVIDER` and assembles it through `from_settings`: `claude-code` is the default, and `fake` gives unit tests and CI deterministic results. Switching backends = one subclass + one registry entry: a skill backend adapts the platform's neutral `work/skills/<name>/` layout into its own form in `stage_skill` and returns a native prefix (Claude links `.claude/skills/<name>` and returns `/{name} `, a generic backend returns an empty string with zero adaptation), and reads `HE_AI_AGENT_BIN`/`HE_AI_AGENT_SETTINGS` in `from_settings` (the generic name wins, unset falls back to the legacy names); the service layer and business code stay untouched.

## Analyze tasks

- There are exactly three task keys: `cluster.review` merges drafts and names them, `cluster.score` rates cluster confidence, and `severity.score` rates severity.
- With drafts, each run makes exactly three bounded calls (zero when there are none); the input is draft summaries plus representative samples, member lists stay in code, and call volume is decoupled from the attribution volume N.
- The failure policy comes from `HE_AI_AGENT_FAILURE_POLICY`: it defaults from the provider, `degrade` for `fake` and `strict` for every other provider (including the default `claude-code`). Under `strict`, a failed call or contract violation records `ai_agent_call` with `outcome=error` and then raises `ClusterAIFailure` with the task and a sanitized reason, so the run fails explicitly at the cluster stage; no fallback confidence/severity is persisted and no successful `clusters_created` is written. `degrade` is used only for `fake` or an explicit setting, falls back to deterministic lexical or formula values, and records a separate `degraded` warn event (`task` and `reason`).

## Submission channel

The agent writes exactly one `result.json5` per turn; collection follows the deterministic ladder strict JSON → JSON5 → json-repair and then Pydantic validation. On validation failure it feeds back the concrete fields and constraints, `analyze` gets exactly one bounded retry, and `edit` (task key `agent.edit`) gets no retry. Contracts and defenses live in [`plans/fullstack-design/07-backend-implementation.md`](../plans/fullstack-design/07-backend-implementation.md) §5.5.1–§5.5.4.

## Edit and patch

The `agent-edit` patch source collects one EditPlan from the provider, applies it deterministically on a scratch mirror, and writes back only the changed files; the candidate commit records the real `git diff`. An evaluation reject ends the turn without an automatic retry.

## Run events

Every outbound call records one `ai_agent_call` run event with these payload fields:

```text
task provider model inputTokens outputTokens totalTokens costUsd latencyMs outcome
sessionId attempts feedbackRetries submissionRounds submissionParsedBy submissionRepaired
submissionParseFailures submissionValidationFailures
```

- `outcome` is `ok`, `degraded` or `error`; `submissionParsedBy` is the final collection pass's ladder tier even when that document later fails validation, and null when nothing was submitted; `submissionRepaired` means the final pass used the repair tier, while `outcome` remains the success signal.
- The parse failure rate is `submissionParseFailures` / `submissionRounds`; a zero `submissionRounds` means nothing was submitted to parse, so the rate does not apply. `feedbackRetries` counts the feedback retries.
- Analyze events land in stage `cluster` step 5 (`step_index=4`), and agent-edit events land in stage `candidate` step 6 (`step_index=5`).
- A failed call keeps usage and latency when a CLI result was parsed; a process-level failure before parsing reports zero usage and an unknown model.
- `/steps/clusters` exposes `algorithm`, `failurePolicy`, `degraded`, and `failure` for a strict failure; the page lists fallback tasks when degraded and the diagnosable cause when strict, and a failed run no longer shows “self-evolution effective”.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `AI_AGENT_PROVIDER` | `claude-code` | Selects the registered subclass; `fake` is for deterministic tests |
| `HE_AI_AGENT_BIN` / `HE_AI_AGENT_SETTINGS` | empty | Generic backend config entry; the generic name wins, unset falls back to `HE_AI_AGENT_CLAUDE_*` |
| `HE_AI_AGENT_CLAUDE_BIN` | `~/.local/bin/claude` | Claude Code CLI path (deprecated alias); deployment injects the stable `current` path |
| `HE_AI_AGENT_CLAUDE_SETTINGS` | empty | Explicit `settings.json` path (deprecated alias); otherwise `CLAUDE_CONFIG_DIR`, then `~/.claude` |
| `HE_AI_AGENT_FAILURE_POLICY` | derived from provider | `strict` (default for real providers) or `degrade` (default for `fake`); an unknown value fails startup |
| `HE_PATCH_SOURCE_MODE` | `placeholder` | Accepts `minimal-config` and `agent-edit`; `agent-edit` needs a configured provider |

Deployment writes the credential to the 0600 `.env` (`ANTHROPIC_API_KEY`) and shared settings; the service passes the environment through to the CLI without reading, persisting, or logging the value. A frontend observability panel is an explicit non-goal.
