# Agent Note: Knowledge-document trigger extraction

Status: implemented

English | [中文](2026-11-16-knowledge-document-triggers.md)

## Problem

M9-01/M9-02/M9-04 already persist Skill, Agent, and Workflow triggers plus object revisions and trigger coordinates in `agent_events`, but knowledge use stays invisible: an ordinary `Read`, a knowledge search, and an MCP retrieval all produce nothing, and `kind` only has `skill|agent|workflow`. Attribution and evolution cannot see which knowledge documents a session read, nor bind a document revision into the evidence chain. Treating every `Read` as a knowledge trigger would pollute the evidence with source-code browsing, while storing document bodies or retrieval chunks would break the rule that trace detail never enters storage.

## Decision

- Add `knowledge` to the event `kind` and to the Session API `SessionEvent` in the same change; `bad_cases.object_type` and `evolution_targets.object_type` stay `skill|agent`, so knowledge events are evidence but not yet an evolution object.
- Knowledge roots are workspace configuration stored in the `workspaces.knowledge_roots` JSON string array: absolute paths that are never the filesystem root `/`, at most 20 per workspace, at most 512 characters each, rejecting `..` and NUL. Space admins write them through the existing `PUT /api/workspaces/{wid}` `knowledgeRoots` field; values are canonicalized to forward slashes, stripped of trailing separators, and deduplicated first. JSON columns carry no server default, and `NULL` equals `[]`. `GET /api/workspaces` returns real paths only to space admins and the global administrator; members/viewers get `[]`.
- An ordinary `Read` becomes an event only when its canonicalized path matches a knowledge root: paths are normalized first (backslashes, duplicate slashes, trailing slash) and then matched by longest prefix with segment boundaries (`/kb` never matches `/kb2`); `Edit`/`Bash` never emit. Document identity is `doc:<sha256(canonical root-relative path)[:32]>`, `retrieval_kind=file_read`, `retrieval_scope` is the matched root, and `source_path` stores the canonical path truncated to 1024. Relative paths never match and the cwd is never guessed.
- MCP recognizes explicit tool names only: `mcp__knowledge__search`, `mcp__knowledge__retrieve`, `mcp__knowledge-base__search`, `mcp__knowledge_base__search`, `mcp__kb__search`, `mcp__kb__retrieve`. There is no fuzzy "name contains knowledge" matching. Every returned document yields one event; `retrieval_kind` separates `mcp_search/mcp_retrieve`, and `retrieval_scope` takes the provider collection, falling back to the adapter default scope.
- Migration `0019` adds `document_id/document_revision/source_path/retrieval_kind/retrieval_scope` (512, matching the configuration limit) plus an `(agent_id, kind, document_id)` index to `agent_events`, and `knowledge_roots` to `workspaces` in the same change. Only id, revision, path, kind, scope, and hashes are stored; document bodies, chunks, and raw MCP responses never enter storage.
- Replay takes the union of `knowledge_roots` from every workspace that reported the root session through `bad_cases.workspace_id`; the union only deduplicates and canonicalizes (`merge_knowledge_roots`) and does not apply the write-side 20-root limit; a local root with no bad case has no roots, and a missing `bad_cases` table degrades to empty roots instead of failing the root. `parser_version` moves 4 → 5, and `event_index` is stably reordered by `(line_no, event_index)` at finalize so result arrival order cannot change coordinates.
- Changing a workspace's roots to a different set clears `source_records.parser_version` for that workspace's reported roots, so the next sync/replay recomputes them; an unchanged set (including reordering) does not trigger. This also covers the "import sessions first, configure roots later" order.
- `document_revision` keeps the provider's raw revision (file reads use `digest:<sha256>` and partial reads `unknown`); `object_revision` follows the shared closed vocabulary: `digest:<sha256>` / `unknown` for file reads and `provider:<raw revision>` / `unknown` for MCP. The two fields are no longer unconditionally equal.

## Alternatives considered

- **Make knowledge an evolution object now**: `object_type=knowledge` would require target configuration, PotentialMatcher, and attribution tri-state in the same slice. This issue delivers evidence only; extending the enum early writes values downstream cannot query; rejected and deferred past M10.
- **Store knowledge roots in a new table or an environment variable**: a table needs a new management endpoint and migration, while an environment variable cannot vary per workspace. The existing workspace configuration channel and permission model make the JSON column the smallest change; both alternatives rejected.
- **Infer knowledge tools from an MCP name prefix or substring**: provider naming has no shared convention, so fuzzy matching would mark unrelated MCP calls as knowledge triggers; rejected in favor of an explicit six-name whitelist.
- **Replay with only the main reporting workspace's roots**: one root session may be reported by several workspaces with different roots, and picking one loses evidence; rejected in favor of the union. Query-time per-space filtering waits for M10.
- **Apply the 20-root write limit to the union**: two workspaces with eleven roots each would fail the whole root replay, with an error that does not point at configuration; rejected in favor of a separate read-side `merge_knowledge_roots` (dedupe, ignore invalid, no count limit) while writes keep the limit.
- **Allow `/` as a knowledge root**: it means "every Read anywhere is knowledge", writing source, configuration, and `.env` paths into evidence and leaking them through shared roots; rejected, validation returns `too_broad`.
- **Return knowledge roots to members**: roots are absolute host paths and deployment topology, and members do not need them; tightening is free; rejected, members/viewers get `[]`.
- **Give a partial read a digest revision**: an incomplete read covers only a fragment, so using it as the document revision would fabricate versions per fragment; rejected in favor of explicit `unknown`, later resolved by a complete read or a provider revision.
- **Store `Read` content or retrieval chunks in the event**: that breaks the no-trace-detail privacy boundary and makes the event table unbounded; rejected in favor of identity, path, revision, and hashes only.

## Consequences

- Workspaces without knowledge roots have no knowledge events; after roots are configured, the service clears the reported roots' parser cursors so the next sync or `pnpm data:replay:sessions` backfills them (parser 5 only affects `claude-code`).
- The event table gains five nullable columns and one index; existing rows read `NULL`. New Session DTO fields are returned only when present, so older clients can ignore them.
- `GET /api/workspaces` and `PUT /api/workspaces/{wid}` now return `knowledgeRoots`; invalid configuration yields `422 KNOWLEDGE_ROOTS_INVALID` with a stable reason and never echoes the path.
- Normalization now reads `bad_cases` to resolve workspace knowledge roots: when the problem-side table is absent it degrades to empty roots, so replay does not fail but those sessions carry no knowledge evidence.
- When one root session is reported by several workspaces, the union means other workspaces' members can see `sourcePath` and `retrievalScope` under this workspace's roots (paths and document existence, never bodies); per-space filtering waits for M10.
- `agent_tree` parent-tool bookkeeping skips `kind=knowledge`, so knowledge calls no longer participate in `DUPLICATE_TOOL_USE_ID` diagnostics; this exemption is required for one retrieval returning many documents.
- The frontend has no knowledge-specific style, legend entry, or Admin roots input: events render as the generic pill and configuration is API-only. Productization (color, legend, form) is a separate issue, not part of this evidence slice.
- Knowledge events remain attribution evidence and cannot yet be selected by PotentialMatcher or target configuration; promoting them requires a new `object_type` slice plus query-time workspace filtering.
