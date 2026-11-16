# Agent Note: Report-bound session sources and runtime projection

Status: implemented

English | [中文](2026-11-16-per-report-session-source.md)

## Problem

A bad-case report used to carry only `sessionId`, so trace backfill depended entirely on one global query service whose contract implied Claude Code's shape and could only default `runtime_key`. Once teams report sessions from different agents, a single global URL cannot route each report to the right upstream, and the m9-06 parser factory never receives the real runtime. Guessing the source from Claude fields inside root-sync would create a second home for runtime identity and push new-agent support into shared traversal and normalization code.

## Decision

- Add an optional `sessionSource = {runtime?, sessionUrlTemplate}` to ingest. The template must be an absolute http(s) URL with exactly one `{sessionId}` placeholder, and the body accepts no headers/token; `runtime` is only a declaration and the envelope remains authoritative.
- Define a single envelope returning `runtime`, `agentKind`, `parentSessionId`, `childSessionIds`, runtime-specific `agentMeta`, and the canonical `trace` in one response. `runtime` is the one vocabulary shared by parsers and session-source adapters.
- Add `third_party_api/session_source/`: `BaseSessionSourceAdapter` projects an envelope onto the runtime-agnostic `SessionInfo`, subclasses implement only `parse_agent_meta`, and `SessionSourceFactory` self-registers and selects by envelope runtime. An unknown runtime raises `UnsupportedTraceRuntime` with no Claude fallback.
- Root-sync selects a source on the first claim and freezes `source_kind/source_snapshot`: a per-report source wins, otherwise the global source is used; retries reuse the snapshot instead of switching to a later-reported URL. An explicit source failure fails the root with a stable `SESSION_SOURCE_*` / `UNSUPPORTED_RUNTIME` code.
- Envelope projection writes `runtime_key`, `agent_kind`, and `agent_meta` into the payload. A main agent may keep the envelope `agentMeta`; a subagent gains `parentAgentId` and keeps an upstream `toolUseId`, then existing replay feeds the parser and tree assembly.
- Move trace canonicalization out of `HttpSessionQuerySource` into a shared `session_query` NDJSON module so both clients share the same re-serialization, duplicate-key rejection, and size/line limits.

## Alternatives considered

- **Use the reported `runtime` to select both adapter and parser directly**: the declaration can be missing or wrong while the envelope is authoritative; rejected in favor of selecting the adapter after the envelope arrives.
- **Store the per-report source only in the root-sync state table**: the ingest row is the factual home of the source and the state row only freezes which snapshot a claim used; rejected to avoid duplicate storage.
- **Fall back to the global source after a failure**: that silently swaps the upstream the reporter specified and hides misconfiguration; rejected, an explicit source failure fails the root.
- **Relax Claude `agentMeta` to arbitrary keys**: provider fields would leak into the shared contract and let a new runtime pass as Claude; rejected, the closed schema stays inside the subclass.
- **Create one HTTP client per root**: connection and retry policy would scatter and the serial lock would lose its process-wide meaning; rejected in favor of a shared client plus one serial lock.

## Consequences

- Reports without `sessionSource` keep the old behavior; a root with a source bypasses the global query service entirely and can sync while that service is unconfigured.
- Adding a runtime still requires both `session_source/<runtime>.py` and `parsers/<runtime>.py`; their runtime keys must agree or the projected payload fails replay with `UNSUPPORTED_RUNTIME`.
- Because retries never switch sources, fixing a URL by re-reporting cannot move an already-claimed root to the new URL; an operator must clear the state row. This is an intentional consistency boundary.
- `source_snapshot` is an internal JSON contract with no separate OpenAPI entry; readers still validate it with a closed model, and a corrupt snapshot fails the root instead of falling back silently.
- A main agent's `agentMeta` reaches the payload; like subagent metadata it must pass the runtime-specific closed schema, and an unknown field rejects the whole envelope.
