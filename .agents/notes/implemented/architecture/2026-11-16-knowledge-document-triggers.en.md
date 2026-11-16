# Agent Note: Knowledge-document trigger extraction

Status: implemented

English | [中文](2026-11-16-knowledge-document-triggers.md)

## Problem

M9-01/M9-02/M9-04 already persist Skill, Agent, and Workflow triggers plus object revisions and trigger coordinates in `agent_events`, but knowledge use stays invisible: an ordinary `Read`, a knowledge search, and an MCP retrieval all produce nothing, and `kind` only has `skill|agent|workflow`. Attribution and evolution cannot see which knowledge documents a session read, nor bind a document revision into the evidence chain. Treating every `Read` as a knowledge trigger would pollute the evidence with source-code browsing, while storing document bodies or retrieval chunks would break the rule that trace detail never enters storage.

## Decision

- Add `knowledge` to the event `kind` and to the Session API `SessionEvent` in the same change; `bad_cases.object_type` and `evolution_targets.object_type` stay `skill|agent`, so knowledge events are evidence but not yet an evolution object.
- Knowledge roots are workspace configuration stored in the `workspaces.knowledge_roots` JSON string array: absolute paths, at most 20 per workspace, at most 512 characters each, rejecting `..` and NUL. Space admins write them through the existing `PUT /api/workspaces/{wid}` `knowledgeRoots` field; values are canonicalized to forward slashes, stripped of trailing separators, and deduplicated first. JSON columns carry no server default, and `NULL` equals `[]`.
- An ordinary `Read` becomes an event only when its path matches a knowledge root: longest prefix with segment boundaries (`/kb` never matches `/kb2`); `Edit`/`Bash` never emit. Document identity is `doc:<sha256(root-relative path)[:32]>`, `retrieval_kind=file_read`, and `retrieval_scope` is the matched root.
- MCP recognizes explicit tool names only: `mcp__knowledge__search`, `mcp__knowledge__retrieve`, `mcp__knowledge-base__search`, `mcp__knowledge_base__search`, `mcp__kb__search`, `mcp__kb__retrieve`. There is no fuzzy "name contains knowledge" matching. Every returned document yields one event; `retrieval_kind` separates `mcp_search/mcp_retrieve`, and `retrieval_scope` takes the provider collection, falling back to the adapter default scope.
- Migration `0019` adds `document_id/document_revision/source_path/retrieval_kind/retrieval_scope` plus an `(agent_id, kind, document_id)` index to `agent_events`, and `knowledge_roots` to `workspaces` in the same change. Only id, revision, path, kind, scope, and hashes are stored; document bodies, chunks, and raw MCP responses never enter storage.
- Replay takes the union of `knowledge_roots` from every workspace that reported the root session through `bad_cases.workspace_id`; a local root with no bad case has no roots. `parser_version` moves 4 → 5, and `event_index` is stably reordered by `(line_no, event_index)` at finalize so result arrival order cannot change coordinates.
- A complete file read yields `document_revision=digest:<sha256>`; a partial or truncated read yields `unknown`. `object_revision` equals `document_revision`.

## Alternatives considered

- **Make knowledge an evolution object now**: `object_type=knowledge` would require target configuration, PotentialMatcher, and attribution tri-state in the same slice. This issue delivers evidence only; extending the enum early writes values downstream cannot query; rejected and deferred past M10.
- **Store knowledge roots in a new table or an environment variable**: a table needs a new management endpoint and migration, while an environment variable cannot vary per workspace. The existing workspace configuration channel and permission model make the JSON column the smallest change; both alternatives rejected.
- **Infer knowledge tools from an MCP name prefix or substring**: provider naming has no shared convention, so fuzzy matching would mark unrelated MCP calls as knowledge triggers; rejected in favor of an explicit six-name whitelist.
- **Replay with only the main reporting workspace's roots**: one root session may be reported by several workspaces with different roots, and picking one loses evidence; rejected in favor of the union. Query-time per-space filtering waits for M10.
- **Give a partial read a digest revision**: an incomplete read covers only a fragment, so using it as the document revision would fabricate versions per fragment; rejected in favor of explicit `unknown`, later resolved by a complete read or a provider revision.
- **Store `Read` content or retrieval chunks in the event**: that breaks the no-trace-detail privacy boundary and makes the event table unbounded; rejected in favor of identity, path, revision, and hashes only.

## Consequences

- Workspaces without knowledge roots and sessions that have not been replayed have no knowledge events; `pnpm data:replay:sessions` backfills them, and parser 5 only affects `claude-code`.
- The event table gains five nullable columns and one index; existing rows read `NULL`. New Session DTO fields are returned only when present, so older clients can ignore them.
- `GET /api/workspaces` and `PUT /api/workspaces/{wid}` now return `knowledgeRoots`; invalid configuration yields `422 KNOWLEDGE_ROOTS_INVALID` with a stable reason and never echoes the path.
- Normalization now reads `bad_cases` to resolve workspace knowledge roots: only environments where the problem-side table exists get knowledge evidence, and tests that build internal tables only must bootstrap the external tables explicitly.
- Knowledge events remain attribution evidence and cannot yet be selected by PotentialMatcher or target configuration; promoting them requires a new `object_type` slice plus query-time workspace filtering.
