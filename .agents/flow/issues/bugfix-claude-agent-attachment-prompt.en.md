# Parse nested attachment prompt_snapshot and propagate parent definitionHash

English | [中文](bugfix-claude-agent-attachment-prompt.md)

```yaml flow
kind: issue
id: bugfix-12
milestone: bugfix
depends:
  - m9-02
  - m9-04
  - m9-07
priority: P2
status: in-progress
scope:
  - apps/api/app/service/acquisition/parsers/**
  - apps/api/app/service/acquisition/agent_tree.py
  - apps/api/tests/**
  - docs/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-21-claude-attachment-prompt-snapshot.md
github:
  number: 471
  url: https://github.com/Shadow-Azure/harness-evolution/issues/471
```

## Background

Agent association in production OpenSpec-cn traces is 0: across the 57 imported Sessions, no tree carries `agent_definition_hash`, and all 73/73 agent events are `objectRevision=unknown`. The platform API only exposed the parsed tree, so it was impossible to distinguish "upstream did not provide the definition" from "the parser did not read it."

On 2026-11-21 we read `bad_cases.session_source` over production root SSH and called the real `sessionUrlTemplate`; the result was:

- the sample is one main agent plus six subagents;
- the child envelope's `trajectory.content` has no top-level `type=prompt_snapshot`;
- the definition body actually lives in `type=attachment`, `attachment.type=prompt_snapshot`, under `attachment.systemPrompt[0]`;
- normalizing `attachment.systemPrompt[0]` with the platform rules yields `c816a39e…` for `code-generator`, `86b6567b…` for `spec-reviewer`, and `3742e03f…` for `code-quality-reviewer`; all 6/6 match the a7ec200 mirror `AGENT.md` digests;
- the child `agentMeta` only contains `{"name": "..."}`, not `promptSnapshot`; the root cause is not a dropped `agentMeta.promptSnapshot`.

There is a second blocker: the child `agentMeta` only has `name`, not `agentType`, while `_agent_revision` requires `agentType`. Even if the attachment fix yields `agent_definition_hash`, `agent_revision` is still None. `agent_tree._apply_agent_revisions` attaches the child's `definition_hash` to the parent `kind=agent` event only when the revision is non-null, so the parent event remains `unknown` and the matcher still misses.

`ClaudeCodeTraceParser.consume_record` calls `_record_agent_definition` only for `record_type in {"prompt_snapshot","api-request-shape"}`; `record_type == "attachment"` is used only for `skill_listing` digests and never checks `attachment.type`. `_definition_body` also reads `record["system"]` for `api-request-shape`, while the real data is under `record["shape"]["system"]`. The direct root cause of the 0 hash is therefore a **Claude parser subclass record-shape gap**, not missing data, a matching bug, or a target configuration problem.

## Goals

- In the Claude Code subclass, recognize `type=attachment` with `attachment.type=prompt_snapshot`, read `attachment.systemPrompt`, and emit `agent_definition_hash` / `definition_source`.
- In `agent_tree._apply_agent_revisions`, attach the child `definition_hash` to the parent `kind=agent` event whenever the hash exists, even when the child revision is None; the matcher uses `definition_hash` to match the target body hash.
- Use the same normalization as the target side so all six OpenSpec-cn agent digests align with the mirror `AGENT.md`.
- Bump `parser_version` so existing payloads replay without re-pulling upstream or changing the database.
- Keep the existing top-level `prompt_snapshot` / `api-request-shape` behavior regression-free.

## Design authority

- [07 §2.3 Normalization](../../../plans/fullstack-design/07-backend-implementation.md#23-归一化行数组--中间结构)
- [07 §2.4 Agent session tree assembly](../../../plans/fullstack-design/07-backend-implementation.md#24-agent-会话树组装)
- [07 §2.6.1 Session-source adapter factory (M9-07)](../../../plans/fullstack-design/07-backend-implementation.md#261-会话来源适配器工厂m9-07)
- [05 §10.5 Report-bound session envelope](../../../plans/fullstack-design/05-api-design.md#105-上报绑定的会话信息-envelopem9-07)

## Implementation

- Add an attachment branch in `ClaudeCodeTraceParser.consume_record`: when `attachment.type == "prompt_snapshot"`, pass `attachment.systemPrompt` to the existing `_record_agent_definition` (synthesize `{"systemPrompt": ...}` or add a private helper).
- Keep `_definition_body` taking the first item of the `systemPrompt` list; the real first item is the target `AGENT.md` body and its hash already matches.
- Use the attachment path only; do not treat `api-request-shape.shape.system` as the definition body because its hash does not match the target.
- Bump `parser_version` from 7 to 8; `source_records.parser_version` triggers replay, and the existing attachment payload can be recomputed directly.
- The parent-event propagation change lives in `agent_tree._apply_agent_revisions`: write `definition_hash` even when revision is empty, without changing the `agent_revision = agentType + isBuiltIn + body hash` identity semantics.
- Add a parser unit test: attachment shape → `agent_definition_hash`; parent agent event → `digest:` revision.
- Add one Agent Note recording the nested-attachment decision and boundary.
- Design docs: `07 §2.3` and `15 §9.2` record the real nested shape; the Agent Note links this issue.

Do not change `AgentMetaFacts`, `TargetObjectType` / `TARGET_FILE_NAMES`, the matcher, database schema, or contracts.

## Implementation steps

1. Add attachment prompt_snapshot recognition and hash emission in `claude_code.py`.
2. Add unit tests for `type=attachment` + `attachment.type=prompt_snapshot` + `systemPrompt` list; assert hash/source, parent revision, and no false positive for attachments without prompt.
3. Bump `parser_version` and confirm replay re-normalizes stored payloads.
4. Add the Agent Note and update flow documentation references if needed.
5. Run focused verification and gates; in a test environment create an agent target and confirm preview association.

## Dependencies and boundary

- Depends on m9-02, m9-04, m9-07.
- Boundary: only the Claude Code parser subclass's recognition of nested attachment `prompt_snapshot`; no object-model, matching-algorithm, database, or upstream-contract change.
- This issue does not include production runs, production replay, or agent-target creation; those are post-acceptance operations.

## Verification

```sh
pnpm test:api -- tests/m9-02-trace-metadata-completion-parser
pnpm lint:api
pnpm typecheck:api
pnpm test:gates
pnpm verify:flow
```

- The new test asserts `agent_definition_hash == c816a39e…` (or the fixture digest), `definition_source == "prompt_snapshot"`, and parent `object_revision == "digest:<hash>"`.
- Existing top-level `prompt_snapshot` / `api-request-shape` tests stay green.
- `pnpm verify:flow` passes with the complete paired issue.

## Acceptance

- A synthetic attachment fixture yields a child `agent_definition_hash`; the parent `kind=agent` event carries the same `definitionHash`, and a `digest:` revision when the child has an `agentType`.
- For the real templateUrl sample, the six children's `attachment.systemPrompt[0]` match `c816a39e…` / `86b6567b…` / `3742e03f…`; the parent event carries the same `definitionHash`; after creating an agent target, the wizard preview associates at least the corresponding Session.
- Existing `prompt_snapshot` / `api-request-shape` paths do not regress; tests, lint, typecheck, and flow gates are green.

## Gates and CI

- `pnpm test:api -- tests/m9-02-trace-metadata-completion-parser`
- `pnpm lint:api`, `pnpm typecheck:api`
- `pnpm test:gates`, `pnpm verify:flow`
- If docs/Agent Note change, run `pnpm verify:docs` and `pnpm record:i18n -- <pair>`.

## Non-goals

- No changes to `AgentMetaFacts`, `TargetObjectType`, `TARGET_FILE_NAMES`, the matcher, or database schema.
- No name-only agent matching and no heuristic guessing of arbitrary fields.
- No handling of top-level envelope `promptSnapshot`, whole-session root-content splitting, or main-agent `agentMeta` mapping to children; those need separate issues.
- No production replay, production agent target/run creation, or production credential/templateUrl changes.
