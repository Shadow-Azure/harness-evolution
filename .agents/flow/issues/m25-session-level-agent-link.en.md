# Session-scoped parser: can_parse trace selection, member state, and parent links

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
  - apps/web/src/components/agent-tree/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/**
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/implemented/architecture/2026-11-20-session-scoped-parser-can-parse.md
github:
  number: 429
  url: https://github.com/Shadow-Azure/harness-evolution/issues/429
```

## Background

The execution flow of production session `226504ab-f005-42ce-a9f5-8313c45d669e` shows three `synthetic-agent` nodes: all three subagents hang off L1412–L1414 instead of their real trigger points L1028 / L1202 / L1411; the tree marks them as synthetic, and the lane DAG stacks all three child lanes at about 78%. The cause is that the envelope `agentMeta` only exposes `name` and omits `toolUseId`, while the current parser is a stateless single-transcript parser; cross-transcript parent links can only be guessed by `agent_tree` from weak fields.

- `TraceParserFactory.create(runtime_key)` selects a subclass only by runtime identity; `BaseTraceParser.normalize(payload)` handles one Agent JSONL at a time; `ClaudeCodeTraceParser` cannot see other transcripts of the same root until `agent_tree.assemble_agent_trees` receives all of them.
- This does not match the intended design: when `ClaudeCodeTraceParser` is created it should already hold the main Agent and all subagent traces of the whole session in member variables, and the base class should add interfaces implemented by the subclass. The previous B design (stateless parser plus a link hook) only fixed parent links and did not realize this session-scoped model.
- In the raw data the parent `toolUseResult.agentId` and the child JSONL top-level `agentId` match 3/3 exactly (`call_6424…→ad5308…`, `call_78b3…→a02a17…`, `call_b302…→a396a3…`), which is enough for the subclass to resolve parent links; when `toolUseId` is present it should still win as authoritative evidence.

Per the user's 2026-11-20 direction, this issue switches to Plan A: the parser is session-scoped and receives all traces of one root in its constructor; parser selection also changes from “runtime_key only” to “based on the trace”, with a new abstract `can_parse` on the base class (the user's `can_parsed`) implemented by each subclass to decide whether it can initialize the trace.

## Goals

- Make `BaseTraceParser` session-scoped: its constructor receives all `TracePayload`s of one root (the main Agent plus every nested subagent) and initializes `self.payloads`, `self.main`, `self.subagents`, and related members; add `normalize_session()` to produce all transcripts and parent links in one call.
- Add the abstract class method `can_parse(payloads) -> bool` on the base class; each subclass implements trace-content detection so a parser can be chosen without relying on `runtime_key`.
- Add trace-based selection to `TraceParserFactory`: evaluate every registered subclass's `can_parse`; instantiate only on a unique match; raise `UnsupportedTraceRuntime` on zero matches and `AmbiguousTraceRuntime` on multiple. `runtime_key` remains metadata and registry identity, not the sole selector.
- Implement `can_parse` in `ClaudeCodeTraceParser` (recognize Claude Code main/subagent JSONL shapes) and resolve parent links inside `normalize_session()` using `self.main` / `self.subagents`: prefer the envelope `toolUseId` (authoritative); when absent, use the parent `toolUseResult.agentId` ↔ child JSONL top-level `agentId` (derived).
- Change `replay` / `local` / `normalize` to load all payloads of a root first, create the session-scoped parser, then call `normalize_session`, and hand transcripts and links to `agent_tree`; keep `synthetic` for missing or ambiguous links.
- Update `plans/fullstack-design/01-architecture.md` §4.1 for the new selection and session lifecycle, add an Agent Note, raise `parser_version`, and replay existing roots.

## Design authority

- [01 §4.1 Trace ingestion and normalization](../../../plans/fullstack-design/01-architecture.md): the current factory selects by runtime and a new runtime only adds a subclass; this issue upgrades selection to trace-based `can_parse` and raises the parser lifecycle to the session, so that section must be revised together.
- [06 §7.1 User turns, messages, and the agent tree](../../../plans/fullstack-design/06-database-design.md): the child agent's `*.meta.json.toolUseId` points at the parent Agent call, and `agentId` is the child identity; this issue uses the two `agentId` values as a fallback when the envelope lacks `toolUseId`.
- [05 §10 Trace query API](../../../plans/fullstack-design/05-api-design.md): the upstream payload contract stays unchanged; this issue only changes HE-side selection, lifecycle, and degradation semantics.

## Implementation

- `parsers/base.py`: `BaseTraceParser.__init__(payloads)` stores the session members (`payloads`, `main`, `subagents`); add the abstract class method `can_parse(payloads)`; add the template `normalize_session()` (normalize each payload → call the subclass's `link_transcripts()` → return transcripts plus `AgentLink`s).
- `parsers/factory.py`: add `for_trace(payloads)` to select uniquely via `can_parse` and instantiate; keep `create(runtime_key, payloads)` as the explicit/test entry; read `CURRENT_PARSER_VERSION` from the registered class instead of probing with a no-arg instance.
- `parsers/claude_code.py`: implement `can_parse` (probe the first JSONL record for `sessionId` / `uuid` / `type` / `message` / `toolUseResult` / `isSidechain` / `agentId` Claude shapes); `normalize_session` resolves parent links with `self.main` / `self.subagents`; prefer `toolUseId`, otherwise the two `agentId` values; raise `parser_version` from 6 to 7.
- `normalize.py` / `replay.py` / `local_sessions.py`: load all payloads of a root first, create the session parser with `TraceParserFactory.for_trace(payloads)`, then call `normalize_session`; keep the single-transcript compatibility entry as a one-payload session.
- `agent_tree.py`: accept the transcripts and links returned by the session parser and only apply the links; read no Claude `agentId` / `toolUseResult` fields; keep `synthetic` for missing or ambiguous links.
- Selection semantics: `can_parse` is a fast shape probe, not a full parse; multiple matches are a contract ambiguity that must be resolved explicitly, never silently by registration order.
- Lifecycle and memory: one parser instance per root holding references to the already-loaded payloads, without copying raw JSONL; release after the session and never reuse across roots; no cross-request cache.
- Tests and docs: add tests for `can_parse` / selection / session members / parent links / the compatibility entry; revise 01 §4.1 and the Agent Note; production verification reads 226504ab only and commits none of its content.

## Implementation steps

1. Define the session `__init__`, abstract `can_parse`, the `normalize_session()` template, and the `AgentLink` return contract in `parsers/base.py`.
2. Implement unique trace selection, `AmbiguousTraceRuntime`, and the version probe in `parsers/factory.py`.
3. Implement `can_parse`, session members, and `normalize_session` parent links in `parsers/claude_code.py`; raise `parser_version`.
4. Change `normalize.py` / `replay.py` / `local_sessions.py` to load all root payloads before creating the session parser and normalizing.
5. Change `agent_tree.py` to receive and apply the session parser's links while keeping the `synthetic` fallback.
6. Add unit and API tests and run the focused gates; replay/backfill after deploy and verify 226504ab.
7. Update 01 §4.1, the Agent Note, and the flow status; include before/after application captures in the PR.

## Dependencies and boundary

- Depends on: m9-06 (parser factory) and m9-03 (relation evidence); both are done.
- Boundary: only HE acquisition parser/factory/agent_tree, the three entry points, tests, and design docs; no upstream envelope change; no database schema / shared contract / frontend change; no change to other runtimes; no production session content or screenshots in the repository.

## Verification

```sh
pnpm test:api -- -k "parser_factory or claude_code_parser or agent_tree or sessions"
pnpm test:gates
pnpm verify:flow
pnpm verify:flow-online
```

- Expected: `can_parse` recognizes Claude traces and rejects non-Claude ones; selection still works with a missing or wrong `runtime_key`, and ambiguity/zero matches produce stable errors; the session parser exposes `self.main` / `self.subagents` during `normalize_session`; a 226504ab-shaped fixture yields four transcripts and three links and the API tree has no synthetic; the compatibility entry and other runtimes do not regress.
- Production acceptance: after deploy, replay 226504ab; `GET .../tree` returns the three child `toolUseId` values `call_6424… / call_78b3… / call_b302…` with `relationConfidence=derived`, and the lane DAG starts the child lanes at L1028 / L1202 / L1411; before/after captures go into the PR.

## Acceptance

- `BaseTraceParser.can_parse` is an abstract class method; `ClaudeCodeTraceParser` implements trace-content detection, rejects non-Claude traces, and selection works without `runtime_key`.
- `TraceParserFactory.for_trace` instantiates only on a unique match; zero matches raise `UnsupportedTraceRuntime`, multiple matches raise `AmbiguousTraceRuntime`, and registration order never silently wins.
- The session parser receives every payload of one root at construction; `self.main` / `self.subagents` are available in `normalize_session`; one call yields four transcripts and three parent links.
- In a 226504ab-shaped fixture neither the tree nor the lane DAG shows `synthetic-agent`, and the three subagents attach to the real `call_…` triggers; missing/duplicate/ambiguous cases still keep `synthetic` and record a stable issue.
- The compatibility entry (single-payload `normalize` / evidence) and other runtimes behave unchanged; raising `parser_version` lets replay rebuild existing trees; no DB / contract / frontend diff.
- Focused tests and flow/document gates pass; 01 §4.1 and the Agent Note are updated; the PR contains before/after evidence.

## Gates and CI

- Hits: `pnpm test:api`, `pnpm test:gates`, `pnpm verify:flow`, `pnpm verify:flow-online`, `pnpm lint:api`, `pnpm typecheck:api`, `pnpm verify:docs`.
- No new dependencies; the scope covers parser, factory, agent_tree, the three entry points, tests, docs, and flow; CI uses synthetic or sanitized fixtures.

## Non-goals

- Do not change the eval-platform envelope or `toolUseId` forwarding (a separate upstream issue).
- Do not change the frontend lane DAG / tree layout or shared contract fields.
- Do not add database columns or migrations; do not change bad-case anchors, attribution, or evolution algorithms.
- Do not commit production session content, screenshots, or credentials; do not add a cross-root parser cache.
