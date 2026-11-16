# Real metadata compatibility and completion-state parsing

English | [中文](m9-02-trace-metadata-completion-parser.md)

```yaml flow
kind: issue
id: m9-02
milestone: m9
depends:
  - m9-01
priority: P0
status: backlog
scope:
  - apps/api/app/service/acquisition/**
  - apps/api/app/fixture_corpus.py
  - fixtures/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 237
  url: https://github.com/Shadow-Azure/harness-evolution/issues/237
```

## Background

Real metadata now contains isBuiltIn, pickedEffortModel, and finished, while subagent JSONL also includes prompt_snapshot, api-request-shape, agent_listing_delta, attributionSkill, and toolUseResult. Closed-set validation currently rejects the whole Session and misses Skill bodies and agent-definition evidence. A root session may also stop on tool use.

## Goals

- Do not reject a whole import on unknown metadata; validate known fields strictly.
- Parse open tool_use calls, child agents without end_turn, and the final task snapshot.
- Extract a stable agent-definition body hash from prompt_snapshot.systemPrompt[0] / api-request-shape.
- Extract a Skill path and body hash from the isMeta + sourceToolUseID injection.
- Extract file path, range, complete, and content hash from toolUseResult (Read/Bash/Edit).
- Separate requested_model, reported_model, and model evidence.

## Design authority

- [15 §9.2, §9.4](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md#92-对象-revision-与模型身份): revisions and completion.
- [07 §2.3–§2.6](../../../plans/fullstack-design/07-backend-implementation.md#2-原始轨迹接入与归一化serviceacquisition): parser factory and normalization.
- [07 §2.6 Multi-runtime parser factory](../../../plans/fullstack-design/07-backend-implementation.md#26-多-runtime-parser-工厂): record/meta/evidence hooks subclasses implement.

## Implementation

- Validate known metadata strictly; redact unknown scalars into meta with warnings.
- Detect tool_use/tool_result pairing gaps.
- Read the last task_reminder snapshot and stop_reason.
- Implement Claude evidence hooks for agent definitions, Skill injection, and file reads; store only hash/path/range.
- Normalize common suffix blocks (subagent permission notice, Notes, token budget) out of the agent-definition hash.

## Implementation steps

1. Add a sanitized real-shape fixture covering prompt_snapshot, skill meta, and toolUseResult.
2. Implement extended metadata, completion, and evidence hooks.
3. Add replay-idempotency, warning-code, and definition/file-hash tests.

## Dependencies and boundary

- Dependency: m9-01
- Boundary: do not assemble relations; do not implement a second runtime.

## Verification

```sh
pnpm test:api -- tests/acquisition; pnpm data:normalize:sessions
```

- The new-field fixture imports.
- A trailing root tool_use yields TOOL_USE_OPEN.
- A child without end_turn yields MISSING_FINAL_REPORT.
- Two tasks of the same agent type yield the same definition hash; runtimes never share hashes.

## Acceptance

- Real metadata drift does not discard the tree.
- Completion, tool errors, and definition evidence remain distinct.
- Skill bodies and agent prompts are not stored; only hashes and provenance are.

## Gates and CI

- API, data, fixture, and flow gates.

## Non-goals

- No raw message or tool-output storage.
- No speculative inference on unknown fields.
- No provider-private fields in common ParsedTranscript fields.
