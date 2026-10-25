# Agent Note: Local Session Payload Import

Status: implemented

English | [中文](2026-10-25-local-session-payload-import.md)

## Problem

Claude Code sessions on a development machine are real input for later normalization, but a session directory also contains payload JSONL, Agent sidecar metadata, tool results, and error text. Scanning every file or trusting filenames can write the wrong Agent, import non-payload state, or overwrite normalization progress during re-import. Full transcript content must not enter CI, logs, or Git.

## Decision

- Development import consumes only root JSONL plus each root's `subagents/agent-*.jsonl` and its exactly paired `.meta.json`; tool results, markers, and error text remain local and are not read. A root main Agent uses the root session id as `agent_id`; Claude may omit `sessionId` on some root lines, but at least one line must declare it and every declaration must match the filename. A subagent `agentId` is checked against both JSONL and filename and is bounded by `VARCHAR(64)`.
- Raw JSONL is stored once under the `(root_session_id, agent_id)` stable key in `trajectory_payloads`; hashes and line counts derive from original bytes. `agent_meta` stores only subagent metadata accepted by the closed schema. All payloads are validated before one transaction writes them, so failure leaves no partial rows.
- `source_records` creates a processing index only and leaves `processed_*` and `last_sync_run_id` unset. `received_at` records first discovery time, while payload `updated_at` derives from the source write time. Re-importing unchanged content performs no writes; changed content updates only its payload without overwriting normalization runtime state or the discovery time.
- The local directory and `data/harness-evolution.sqlite` are gitignored. Commands emit only root/JSONL/subagent/payload aggregates, never transcript text, source paths, or connection strings; filesystem failures also strip path details. Production and live phases are rejected before scanning or connecting.

## Alternatives considered

- Copy every local file into fixtures: centralized but commits real transcript content and makes CI depend on personal data; rejected.
- Trust filenames when writing rows: faster but allows mismatched JSONL identity to poison the Agent tree; rejected.
- Mark `source_records` processed: makes local seeding look complete but later normalization would skip payloads; rejected.
- Insert without update: idempotent for identical content but forever stale after a source correction; rejected.

## Consequences

- Local real-data acceptance reports 4 roots, 66 JSONL files, 62 subagents, and 66 payload rows at approximately 49.5 MiB; CI uses a small synthetic directory to verify the same contract.
- New legitimate Claude sidecar types require an assessment of payload pairing; non-payload files are ignored by default and never become runtime sources.
- Normalization, parser versions, and session-tree construction remain later acquisition issues; this import only prepares raw payloads and unprocessed indexes.
