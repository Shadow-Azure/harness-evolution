# Trace parent links: session-level hook implemented by ClaudeCodeTraceParser

English | [中文](m25-session-level-agent-link.md)

```yaml flow
kind: issue
id: m25-01
milestone: m25
depends:
  - m9-06
  - m9-03
priority: P1
status: ready
scope:
  - apps/api/app/service/acquisition/**
  - apps/api/tests/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 429
  url: https://github.com/Shadow-Azure/harness-evolution/issues/429
```

## Background

The execution flow of production session `226504ab-f005-42ce-a9f5-8313c45d669e` shows three `synthetic-agent` nodes: all three subagents hang off L1412–L1414 instead of their real trigger points L1028 / L1202 / L1411; the tree marks them as synthetic, and the lane DAG stacks all three child lanes at about 78%.

The directly verified causes:

- The upstream session envelope only exposes `name` in `agentMeta` and omits `toolUseId`; in the raw data, the parent `toolUseResult.agentId` and the child JSONL top-level `agentId` match 3/3 exactly (`call_6424…→ad5308…`, `call_78b3…→a02a17…`, `call_b302…→a396a3…`), but HE does not read either field today.
- `BaseTraceParser` only has the single-transcript `normalize(payload)`; `ClaudeCodeTraceParser` cannot see other transcripts of the same root; `agent_tree` can only use the envelope's `parent_tool_use_id` / `parent_agent_id` and falls back to `append_synthetic_parent_event` when they are absent.
- This does not match the intended design (“the subclass sees the whole session; the base class adds an interface and the subclass implements it”): there is no session-level link hook, so cross-agent runtime evidence has nowhere to go. The missing upstream `toolUseId` is the primary cause; this issue closes the HE design gap and adds a verifiable derived fallback.

## Goals

- Add a session-level `link_transcripts` hook to `BaseTraceParser`, returning empty by default and leaving other runtimes unchanged.
- Implement the hook in `ClaudeCodeTraceParser`: prefer the envelope `toolUseId` (the existing authoritative path); when it is absent, derive links from the parent `toolUseResult.agentId` ↔ child JSONL top-level `agentId`.
- Call the hook per root from `assemble_agent_trees` and apply its links in `_assemble_root`; keep `synthetic` for missing or ambiguous links instead of inventing a parent.
- Do not change the upstream envelope, the database schema, shared contracts, or the frontend; rebuild existing roots by raising `parser_version` and replaying.

## Design authority

- [01 §4.1 Trace ingestion and normalization](../../../plans/fullstack-design/01-architecture.md): `TraceParserFactory` selects a subclass by runtime and adding a runtime only adds a subclass without changing shared replay/agent_tree; this issue turns the cross-agent extension point into a base-class hook invoked by the generic assembler.
- [06 §7.1 User turns, messages, and the agent tree](../../../plans/fullstack-design/06-database-design.md): the child agent's `*.meta.json.toolUseId` points at the parent Agent call, and `agentId` is the child identity; this issue uses the two `agentId` values as a fallback when the envelope lacks `toolUseId`.
- [05 §10 Trace query API](../../../plans/fullstack-design/05-api-design.md): the upstream payload contract stays unchanged; this issue only defines the degradation semantics when the envelope omits the field.

## Implementation

- `parsers/base.py`: add `AgentLink` (`child_agent_id`, `parent_tool_use_id`, `confidence`) and a default empty `BaseTraceParser.link_transcripts(transcripts)`; add typed fields to `ParsedTranscript` for the native `agentId` and the parent `tool_result.agentId` map (`native_agent_id`, `agent_result_ids`).
- `parsers/claude_code.py`: write the child transcript's top-level `agentId` into `native_agent_id`; map the parent `toolUseResult.agentId` by `tool_use_id` into `agent_result_ids`; implement `link_transcripts` to return only uniquely resolvable `derived` links and drop conflicts/missing values; raise `parser_version` from 6 to 7.
- `agent_tree.py`: `assemble_agent_trees` creates the parser by each root's `runtime_key` and calls `link_transcripts`; `_assemble_root` looks up the link when `parent_tool is None`, sets `parent_tool`, and marks `derived`; otherwise keeps `synthetic`.
- Preserve precedence: the envelope `toolUseId` / authoritative relation is unchanged; derived only fills gaps; `synthetic` still covers missing and ambiguous cases and never overrides an existing authoritative link.
- Tests: a main + 3 subagents fixture, missing/duplicate/ambiguous/no-link branches, and API tree assertions; production verification reads 226504ab only and does not commit its content.

## Implementation steps

1. Define `AgentLink`, the `ParsedTranscript` fields, and the default `BaseTraceParser.link_transcripts` in `parsers/base.py`.
2. Extract both `agentId` values in `parsers/claude_code.py`, implement `link_transcripts`, and raise `parser_version`.
3. Call the hook from `assemble_agent_trees` in `agent_tree.py` and pass its links into `_assemble_root`.
4. Apply derived links in `_assemble_root` while preserving the authoritative / derived / synthetic precedence.
5. Add unit and API tests, run the focused gates, then replay/backfill after deploy and verify 226504ab.
6. Update the Agent Note and flow status; include before/after application captures in the PR.

## Dependencies and boundary

- Depends on: m9-06 (parser factory) and m9-03 (relation evidence); both are done.
- Boundary: only HE acquisition parser/agent_tree and tests; no upstream envelope change; no database schema / shared contract / frontend change; no change to other runtimes; no production session content or screenshots in the repository.

## Verification

```sh
pnpm test:api -- -k "claude_code_parser or agent_tree or sessions"
pnpm test:gates
pnpm verify:flow
pnpm verify:flow-online
```

- Expected: unit tests cover the main + 3 subagents fixture with 3/3 links; ambiguous/missing cases fall back to synthetic; the API tree has no synthetic; other runtimes and existing fixtures do not regress; the online flow check is consistent.
- Production acceptance: after deploy, replay 226504ab; `GET .../tree` returns the three child `toolUseId` values `call_6424… / call_78b3… / call_b302…` with `relationConfidence=derived`, and the lane DAG starts the child lanes at L1028 / L1202 / L1411; before/after captures go into the PR.

## Acceptance

- `BaseTraceParser.link_transcripts` returns empty by default; runtimes that do not implement it behave unchanged, and the `synthetic` fallback still covers missing and ambiguous links.
- `ClaudeCodeTraceParser` extracts 3/3 `agentId` values from the raw JSONL and produces unique derived links; `agent_tree` attaches the three subagents to the real `call_…` triggers, and neither the tree nor the lane DAG shows `synthetic-agent`.
- Missing links, duplicate `agentId`, and one `agentId` with multiple parents (ambiguous) keep `synthetic` and record a stable issue instead of mis-attaching.
- Raising `parser_version` lets replay rebuild existing trees; no DB / contract / frontend diff; focused tests and flow/document gates pass; the PR contains before/after evidence.

## Gates and CI

- Hits: `pnpm test:api`, `pnpm test:gates`, `pnpm verify:flow`, `pnpm verify:flow-online`, `pnpm lint:api`, `pnpm typecheck:api`, `pnpm verify:docs`.
- No new dependencies; the scope covers parser, agent_tree, API tests, docs, and flow; CI uses synthetic or sanitized fixtures.

## Non-goals

- Do not change the eval-platform envelope or `toolUseId` forwarding (a separate upstream issue).
- Do not change the frontend lane DAG / tree layout or shared contract fields.
- Do not add database columns or migrations; do not change bad-case anchors, attribution, or evolution algorithms.
- Do not commit production session content, screenshots, or credentials.
