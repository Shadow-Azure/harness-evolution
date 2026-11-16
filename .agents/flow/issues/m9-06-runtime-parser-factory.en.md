# Multi-agent trace parser factory and runtime identity

English | [中文](m9-06-runtime-parser-factory.md)

```yaml flow
kind: issue
id: m9-06
milestone: m9
depends:
  - m7-02
priority: P0
status: done
scope:
  - apps/api/app/service/acquisition/**
  - apps/api/app/api/acquisition.py
  - apps/api/app/db/**
  - apps/api/alembic/**
  - packages/contracts/**
  - apps/api/tests/**
  - tests/**
  - docs/**
  - plans/**
  - plans/fullstack-design/**
  - plans/ui-prototype-v2/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 277
  url: https://github.com/Shadow-Azure/harness-evolution/issues/277
```

## Background

`service/acquisition/normalize.py` only understands Claude Code `assistant/user/attachment` records, `isMeta`, `message.content`, and Claude subagent `meta.json`; `local_sessions.py` also validates Claude metadata directly. `trajectory_payloads.source_type` only means the ingestion channel (`http_api/script`), not the AI agent runtime, and `parser_version` is a global integer. Adding `runtime == ...` branches to the single normalizer would force changes across parsing, replay, version checks, and database uniqueness when a second agent is introduced.

M9 also needs object revisions based on agent/skill definitions and file reads. Without an independent runtime identity first, evidence, potential matching, and attribution caches would mix data from different agents.

## Goals

- Introduce `TraceParserFactory`, `BaseTraceParser`, and `ClaudeCodeTraceParser`, moving Claude-specific parsing into a subclass.
- Carry `runtime_key` through payloads, source cursors, Sessions, and replay while keeping `source_type` as the ingestion channel.
- Interpret `parser_version` per runtime so a new runtime is not compared against Claude's global version.
- Emit a stable issue code for unknown runtimes instead of silently falling back to Claude.
- Make a new runtime only add a parser subclass and register it, without editing `normalize.py`, `replay.py`, or `agent_tree.py`.

## Design authority

- [07 §2.6 Multi-runtime parser factory](../../../plans/fullstack-design/07-backend-implementation.md#26-多-runtime-parser-工厂): base class, factory, subclasses, and registration.
- [06 §3.0.1 Runtime identity](../../../plans/fullstack-design/06-database-design.md#301-runtime-身份与-parser-版本): `runtime_key`, per-runtime `parser_version`, and uniqueness.
- [15 §9.2 Object revision and model identity](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md#92-对象-revision-与模型身份): evidence fields separated from runtime version.

## Implementation

- Add `app/service/acquisition/parsers/`: `base.py`, `factory.py`, `claude_code.py`; discover and register subclasses when the package loads.
- `BaseTraceParser` owns JSONL framing, bad-line issues, privacy boundary, counters, and finalization; subclasses interpret records, metadata, events, and evidence.
- Register with `@TraceParserFactory.register`; duplicate `runtime_key` fails fast; unknown runtime raises `UnsupportedTraceRuntime`.
- Add `runtime_key` to `trajectory_payloads`, `source_records`, and `session_families`, backfilling existing rows as `claude-code`; include runtime in the pending check.
- Pass `runtime_key` through `RootPayload`, replay, and the acquisition API; keep a compatibility `normalize_transcript` facade.
- Add `BaseTraceParser.extract_evidence()` as an optional M9 hook; this issue only establishes the interface, while Claude agent/skill/file evidence is filled by M9-02/M9-04.

## Implementation steps

1. Write failing tests for factory registration, duplicate keys, unknown runtime, and default Claude behavior.
2. Extract `BaseTraceParser` and `ClaudeCodeTraceParser` while keeping existing normalize tests green.
3. Add the runtime_key migration, `RootPayload` field, and per-runtime parser version query.
4. Wire replay and the acquisition API, and emit a sync issue for unknown runtimes.
5. Add an extension test for a fake runtime registered only through a subclass, plus an Agent Note.

## Dependencies and boundary

- Dependency: m7-02
- Non-goal: do not implement a second real runtime; do not parse M9 agent/skill/file evidence bodies; do not change frontend presentation.

## Verification

```sh
pnpm test:api -- tests/acquisition tests/replay
pnpm test:db
pnpm contract:check
pnpm verify:flow
```

- All Claude fixtures keep their existing counts and events.
- A test-only fake runtime is selected by replay after only registering a subclass.
- An unknown runtime yields `UNSUPPORTED_RUNTIME` and never enters the Claude parser.
- Bumping one runtime's parser version does not replay another runtime.

## Acceptance

- Adding a runtime requires no edits to shared normalization/replay files.
- `runtime_key` is consistent across payloads, source cursors, Sessions, and replay.
- `source_type` is no longer treated as a runtime.
- Existing E2E, database, and contract gates do not regress.

## Gates and CI

- API unit tests, both database dialects, contracts, flow, and docs gates.

## Non-goals

- Do not implement Codex or another real agent's parsing rules.
- Do not leak provider-specific fields into common `ParsedTranscript` fields.
- Do not persist messages, tool output, or agent definition bodies.
