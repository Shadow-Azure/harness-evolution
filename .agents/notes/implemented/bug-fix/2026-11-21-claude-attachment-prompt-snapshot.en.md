# Agent Note: Claude Code nested attachment prompt snapshot

Status: implemented

English | [中文](2026-11-21-claude-attachment-prompt-snapshot.md)

## Problem

Claude Code subagent definition evidence has been described in design docs and the parser as a top-level `prompt_snapshot.systemPrompt[0]` (or `api-request-shape.system`). A 2026-11-21 measurement of the production `sessionUrlTemplate` showed the real shape is `type=attachment`, `attachment.type=prompt_snapshot`, `attachment.systemPrompt[0]`: there is no top-level `type=prompt_snapshot` record, and `agentMeta` only carries `name`. The parser only checks top-level `type=prompt_snapshot` / `api-request-shape`, so every agent event lacks `definition_hash` and agent targets cannot be associated.

For all six measured subagents, the SHA-256 of `attachment.systemPrompt[0]` matches the a7ec200 mirror `AGENT.md` exactly (code-generator `c816a39e…`, spec-reviewer `86b6567b…`, code-quality-reviewer `3742e03f…`). The data exists; the gap is the parser's shape recognition.

There is a second blocker: the child `agentMeta` only has `name`, not `agentType`, while `_agent_revision` requires `agentType`. Even after the attachment fix produces a body hash, `agent_revision` remains None; `_apply_agent_revisions` only attaches the child's `definition_hash` to the parent `kind=agent` event when the revision is non-null, so the parent event stays `unknown` and the matcher still misses.

## Decision

- Claude Code `prompt_snapshot` has two equivalent shapes: top-level `type=prompt_snapshot` with `systemPrompt`, and `type=attachment` with `attachment.type=prompt_snapshot` and `attachment.systemPrompt`.
- The parser prefers `prompt_snapshot` (both shapes are equivalent); `definition_source` remains `prompt_snapshot`, with no new enum value.
- `api-request-shape.system` remains a compatibility fallback; the measured `api-request-shape.shape.system` is a runtime system snapshot whose hash does not match the target `AGENT.md`, so it must not override `prompt_snapshot` or serve as this slice's definition source.
- The change must also make `agent_tree._apply_agent_revisions` attach the child `definition_hash` to the parent `kind=agent` event whenever the hash exists, even when the child revision is None; the matcher then matches the body hash through `definition_hash`, without changing the `agentType + isBuiltIn + body hash` revision semantics.
- This is therefore not a pure Claude-subclass fix: it needs one base propagation change in `apps/api/app/service/acquisition/agent_tree.py`; a `parser_version` bump still triggers replay, with no database, contract, or matcher change.
- Design docs [07 §2.3](../../../../plans/fullstack-design/07-backend-implementation.md#23-归一化行数组--中间结构) and [15 §9.2](../../../../plans/fullstack-design/15-v1-v2-gap-analysis.md#92-对象-revision-与模型身份) now record this fact.

## Alternatives considered

- **Consume only `agentMeta.promptSnapshot`**: production `agentMeta` only has `name`; that path cannot explain the measured data or match the six agents.
- **Match by agent name only**: the same name may map to different definitions across versions, attributing the wrong version to the current target; identity must be the body hash.
- **Treat `api-request-shape.shape.system` as the definition body**: its measured hash does not match the target `AGENT.md`; using it would produce a wrong identity.
- **Split whole root content by `agentId`**: this data is a per-agent envelope and needs no split; that approach would expand the issue into the session model.

## Consequences

- Issue [#471](https://github.com/Shadow-Azure/harness-evolution/issues/471) tracks the parser subclass fix and the `agent_tree` `definition_hash` propagation; this PR implements both, so the parent `kind=agent` event carries the body hash even without a target revision.
- Existing top-level `prompt_snapshot` / `api-request-shape.system` compatibility is unchanged; `shape.system` is not promoted to a definition source.
