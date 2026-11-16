# Agent Note: Multi-runtime parser factory and runtime identity

Status: implemented

English | [中文](2026-11-16-multi-runtime-parser-factory.md)

## Problem

Claude Code parsing rules lived directly in `normalize.py`, and `local_sessions.py` hard-coded the closed Claude `meta.json` schema on the import path. Adding a second AI agent by appending `runtime == ...` branches to the single normalizer would change parsing, replay, version checks, and database uniqueness together; `trajectory_payloads.source_type` also only means the `script` / `http_api` ingestion channel and cannot express which agent produced a trace. M9 also needs to distinguish runtimes in evidence, object revisions, and attribution caches, so without an independent identity the data would inevitably mix.

## Decision

- Add `service/acquisition/parsers/`: `BaseTraceParser` fixes JSONL framing, bad-line issues, counters, and finalization while subclasses implement only `consume_record` / `parse_agent_meta`; `TraceParserFactory` registers and selects parsers by `runtime_key`, and `parsers/__init__.py` auto-discovers sibling modules at package import. A new runtime only adds one subclass file plus `@TraceParserFactory.register`; shared normalize, replay, and agent_tree stay untouched.
- `normalize_transcript(...)` remains a compatibility facade defaulting to `claude-code`, and new callers pass `runtime_key` explicitly; `extract_evidence()` is an optional M9 hook returning an empty tuple for now, leaving Claude agent/skill/file evidence to M9-02/M9-04.
- `runtime_key` runs through `trajectory_payloads`, `source_records`, `session_families`, `agents`, and replay: the payload primary key and source unique key become `(runtime_key, root_session_id, agent_id)`, each Session records its producing runtime, and Agent nodes inherit their root Session runtime. The migration backfills existing rows as `claude-code`.
- `parser_version` comes from the parser class, and `source_records.parser_version` is compared only with the current version of the same runtime; upgrading one runtime replays only its payloads while the other runtime's cursors and Sessions stay unchanged.
- An unknown runtime raises `UnsupportedTraceRuntime`; replay records a stable `UNSUPPORTED_RUNTIME` instead of silently falling back to Claude. A root that mixes runtimes is rejected during assembly with `MIXED_TRACE_RUNTIME`.
- `source_type` still means only the ingestion channel and never selects a parser.

## Alternatives considered

- **Add per-runtime if/else inside `normalize.py`**: every new agent would edit shared parsing and replay files and the branches would keep spreading; rejected.
- **Fall back to Claude for an unknown runtime**: incompatible JSONL would be reported as a successful parse, destroying evidence trust; rejected.
- **Keep a global `parser_version`**: a Claude upgrade would force replay of every other runtime, preventing independent evolution; rejected.
- **Let new runtimes reuse private `ParsedTranscript` fields**: provider fields would leak into the shared contract; rejected.
- **Implement a real second runtime or evidence bodies in M9-06**: outside this issue's delivery boundary; establish the extension point and identity first and leave those to later issues.

## Consequences

- Only one production parser exists today; a fake-runtime test proves that adding a runtime needs no shared normalization/replay/agent_tree edits.
- Unknown-runtime payloads stay pending forever because no parser can advance them; this is an intentional operational signal rather than a silent swallow.
- `session_families.id` is still a global primary key, so one root session id cannot coexist across runtimes; upstream does not produce that identity today, and a composite key can be evaluated if it appears.
- The evidence hook has no real content yet; `agent_definition_hash`, Skill bodies, and file-read evidence land in M9-02/M9-04.
- `trajectory_payloads` is written externally; the runtime_key migration relies on a default backfill, and an external writer must emit runtime explicitly after upgrading or every row will be treated as Claude.
- Legacy `source_type` semantics remain unchanged, and the frontend does not display runtime yet.
