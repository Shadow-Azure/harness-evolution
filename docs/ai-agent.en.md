# AI Agent Outbound Layer

English | [中文](ai-agent.md)

Self-evolution review, scoring and patch generation call models through one outbound layer; installation and model setup live in [claude-code.en.md](claude-code.en.md).

## Layering

- `apps/api/app/third_party_api/ai_agent/` is the single outbound seam: business services call only `build_agent_provider`, never import a vendor module, and never branch on a backend name.
- `AIAgentProvider` defines contracts only; its two capability faces are `analyze` (structured analysis) and `edit_workspace` (a submitted edit plan).
- The factory selects a registered subclass by `AI_AGENT_PROVIDER`: `claude-code` is the default, and `fake` gives unit tests and CI deterministic results; a new backend is one subclass plus one registry entry.

## Analyze tasks

- There are exactly three task keys: `cluster.review` merges drafts and names them, `cluster.score` rates cluster confidence, and `severity.score` rates severity.
- With drafts, each run makes exactly three bounded calls (zero when there are none); the input is draft summaries plus representative samples, member lists stay in code, and call volume is decoupled from the attribution volume N.
- When a call fails or its output violates the contract, that task degrades to deterministic lexical or formula values and records a separate `degraded` warn event (`task` and `reason`).

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

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `AI_AGENT_PROVIDER` | `claude-code` | Selects the registered subclass; `fake` is for deterministic tests |
| `HE_AI_AGENT_CLAUDE_BIN` | `~/.local/bin/claude` | Claude Code CLI path |
| `HE_PATCH_SOURCE_MODE` | `placeholder` | Accepts `minimal-config` and `agent-edit`; `agent-edit` needs a configured provider |

Deployment writes model credentials to `~/.claude`, and the service process never reads them. A frontend observability panel is an explicit non-goal.
