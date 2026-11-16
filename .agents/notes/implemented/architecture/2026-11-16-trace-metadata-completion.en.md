# Agent Note: Real metadata compatibility, completion state, and definition evidence

Status: implemented

English | [中文](2026-11-16-trace-metadata-completion.md)

## Problem

Real Claude Code sessions now carry `isBuiltIn`, `pickedEffortModel`, `finished`, and other new fields in `meta.json`, while subagent JSONL also injects `prompt_snapshot`, `api-request-shape`, Skill bodies, and `toolUseResult`. The old closed metadata validation rejected the entire Session, and the parser could only see text and tool counts. It could not express a root stopped on an unreturned `tool_use`, a child without `end_turn`, or a task snapshot with unfinished items, and it had no stable fingerprints for Agent or Skill definitions or file reads. Parse health `status` had to carry execution completion too, so real failures were hidden by ordinary tool errors.

## Decision

- Metadata validation becomes "strict for known fields, degrade for unknown fields": `agentType`, `description`, `spawnDepth`, `model`, and other known fields keep their type and column-length checks; unknown scalars are credential-redacted, control-character stripped, and length-truncated into `agents.meta`, unknown objects/arrays are dropped, and a stable `UNKNOWN_AGENT_METADATA` warning is emitted. `isBuiltIn`, `pickedEffortModel`, and `finished` become known fields.
- Execution completion is derived only from explicit evidence: assistant `message.stop_reason` of `end_turn` records `completed/end_turn`; `tool_use` with unpaired calls records `interrupted/tool_use_open`, and without unpaired calls records `interrupted/missing_report`; interrupted stop reasons record `external_interrupted`; API-error messages record `failed/external_failed`. Legacy payloads without `stop_reason` stay `legacy_unknown`; completion is never guessed from "the last record is an assistant".
- Stable issue codes `TOOL_USE_OPEN`, `MISSING_FINAL_REPORT`, and `TASK_SNAPSHOT_PENDING` appear only when their explicit evidence exists; task snapshots read pending/in-progress counts from `task_reminder` or `toolUseResult.task` without storing task text.
- Agent definitions come from `prompt_snapshot.systemPrompt[0]` or `api-request-shape.system`; common permission, Notes, and token-budget suffixes are stripped before hashing. When `isBuiltIn` is true only `definition_source=builtin` is recorded, without a body hash.
- Skill bodies come from the `isMeta + sourceToolUseID` injection, storing path and normalized body hash; file reads come from Read/Edit `toolUseResult`, storing path, 1-based range, completeness, and content hash, and Bash only when its result carries a file identity. Evidence structures hold hashes, paths, ranges, and provenance, never bodies.
- Parse results reach existing evidence columns: `session_families`/`agents` receive completion state, `agents` receives the Agent definition hash and source, and Skill events receive `definition_hash`. File-read paths/ranges have no column yet and stay in parser evidence; object revisions, trigger coordinates, relation confidence, and knowledge-event columns stay with M9-03/M9-04/M9-05.
- Session-level completion aggregates as "any failed → failed; any interrupted → interrupted; any legacy_unknown → legacy_unknown; otherwise completed", excluding synthetic workflow nodes; `end_reason` prefers the main Agent's reason.
- `ClaudeCodeTraceParser.parser_version` rises to 2 so existing claude-code payloads gain the new evidence on the next sync/replay; other runtimes are unaffected.
- Requested and reported models stay separate: `requested_model` comes from `meta.model`/`pickedEffortModel`, `reported_model` from the assistant's actual model; when both are concrete, different identities, `MODEL_EVIDENCE_CONFLICT` is emitted and neither overwrites the other.

## Alternatives considered

- **Keep the closed metadata schema and add new fields one by one**: the next provider drift would still reject whole trees, violating "drift must not discard the tree".
- **Infer completion from `ended_with_assistant`**: legacy payloads would be marked completed, turning "unknown" into "completed" and breaking evidence semantics.
- **Store definition and file bodies in the database**: bodies are provider-private and would amplify privacy and storage risk; keep only hashes, paths, and provenance.
- **Add path/range columns to agent_events now**: the 06 design leaves knowledge-document `source_path` to M9-05; this slice keeps paths and ranges in parser evidence to avoid fixing a query shape early.
- **Defer the parser_version bump to M9-04**: that would make the new evidence apply only to new payloads after M9-02 ships, while existing real sessions stay `legacy_unknown`; a parsing-semantics change should replay its own runtime.
- **Treat every Bash output as a file read**: Bash results have no reliable file identity, and guessing a path would create false evidence; record only results that explicitly carry a file structure.

## Consequences

- File-read paths/ranges currently exist only in parser evidence and are not yet queryable through the API or database; M9-05 will connect them when knowledge-event columns are needed.
- Legacy payloads without explicit `stop_reason` stay `legacy_unknown`; clients must treat them as "unknown", not "completed".
- The claude-code parser_version moves from 1 to 2, so the first sync after deployment replays that runtime's existing source_records; this is the expected cost.
- `agents.meta` may now hold truncated unknown scalar fields; field names enter the `UNKNOWN_AGENT_METADATA` warning, but values never reach logs or the API.
- Session-level `execution_outcome` and parse health `status` remain independent axes; the UI and attribution must choose explicitly when reading.
- Relation grading, object revisions, trigger coordinates, and knowledge documents remain in M9-03, M9-04, and M9-05; this Note does not claim they are available yet.
