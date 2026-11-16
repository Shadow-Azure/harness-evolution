# Per-report session source field and multi-runtime session source adapter factory

English | [中文](m9-07-per-report-session-source.md)

```yaml flow
kind: issue
id: m9-07
milestone: m9
depends:
  - m9-06
priority: P1
status: ready
scope:
  - apps/api/app/third_party_api/session_source/**
  - apps/api/app/third_party_api/session_query/**
  - apps/api/app/service/acquisition/**
  - apps/api/app/service/workspaces/**
  - apps/api/app/api/ingest.py
  - apps/api/app/db/**
  - apps/api/app/alembic/**
  - apps/api/app/errors.py
  - apps/api/app/main.py
  - packages/contracts/**
  - apps/api/tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 282
  url: https://github.com/Shadow-Azure/harness-evolution/issues/282
```

## Background

Today a bad-case report (`POST /api/workspaces/{wid}/bad-cases`) carries only problem fields plus `sessionId`; trajectory backfill depends on the single globally configured query service (`HE_SESSION_QUERY_BASE_URL` plus a service token, two endpoints: children and trajectory), and that contract implicitly assumes Claude Code: `BadCaseRootSyncService` writes payloads with the default `runtime_key` of `claude-code`, and the reporter has no channel to declare which AI agent produced the session or where to download it.

That assumption breaks with multiple upstreams: different teams use different agents (Claude Code, opencode, and later ones) whose session stores differ fundamentally — Claude Code is JSONL lines plus `*.meta.json`; opencode is session/message/part objects (`parent_id` for parentage, `modelID/providerID` for models, tool parts for calls). A single global URL can neither route a report to the right upstream nor hand the m9-06 `TraceParserFactory` the real `runtime_key`.

## Goals

- Add an optional `sessionSource` field (dict) to the report API: it carries the URL template for downloading session info by sessionId, plus an optional runtime pre-declaration.
- Define a single-endpoint "session info envelope": one call returns runtime identity, agent metadata, parent/child relations, and the canonicalized trajectory; the `runtime` field decides how the key-value content is interpreted.
- Build `SessionSourceFactory`, `BaseSessionSourceAdapter`, and `ClaudeCodeSessionSourceAdapter`, mirroring the m9-06 parser factory: a new agent adds exactly one subclass file plus registration, with no changes to shared root-sync/normalize code.
- Root-sync picks a source per root: per-report source first, global configured source as fallback; a source snapshot lands on the state table so retries keep the same source.
- Keep runtime identity single-homed: envelope `runtime` → source adapter → `TraceParserFactory` selects the parser; unknown runtimes fail stably and never fall back to Claude.

## Design authority

- [05 §3.8 bad case ingest](../../../plans/fullstack-design/05-api-design.md#38-bad-case-上报): report body contract and where the new field lands.
- [05 §10.1 session trajectory package](../../../plans/fullstack-design/05-api-design.md#101-会话轨迹包核心): the existing single-endpoint session package draft; this issue generalizes it into per-report binding with runtime typing.
- [06 §3.0.1 runtime identity](../../../plans/fullstack-design/06-database-design.md#301-runtime-身份与-parser-版本): the runtime_key vocabulary and the parser selection key.
- [06 §4.1 bad_cases](../../../plans/fullstack-design/06-database-design.md): problem table column evolution.
- [07 §2.6 multi-runtime parser factory](../../../plans/fullstack-design/07-backend-implementation.md#26-多-runtime-parser-工厂): factory, base class, self-registration, and fail-fast patterns.
- [11 §3 external query contract](../../../plans/fullstack-design/11-bad-case-session-sync.md#3-外部查询服务契约): serial lock, limits, and error semantics of the existing two endpoints.
- [11 §3.2 endpoint 2](../../../plans/fullstack-design/11-bad-case-session-sync.md#32-接口-2单-agent-轨迹): NDJSON canonicalization and size limits, reused here.
- [11 §4.2 agent_meta and parent edge](../../../plans/fullstack-design/11-bad-case-session-sync.md#42-agent_meta-与父子边): the parentAgentId fallback anchoring.
- [11 §5.1 bad_case_root_sync table](../../../plans/fullstack-design/11-bad-case-session-sync.md#51-表-bad_case_root_sync): state table evolution.

## Implementation

**Report field**: `BadCaseIngest` gains an optional `sessionSource` (camelCase, `extra="forbid"`, validation failures answer 422):

```json
{
  "runtime": "claude-code",
  "sessionUrlTemplate": "https://trace.internal/api/sessions/{sessionId}"
}
```

- `sessionUrlTemplate` is required: http/https only, length ≤ 2048, and the `{sessionId}` placeholder appears exactly once; no headers/token credential fields are accepted — authorization rides on short-lived signatures embedded in the template itself.
- `runtime` is optional: `^[a-z0-9][a-z0-9-]{0,31}$`, a pre-declaration only; the envelope wins, and a mismatch records a diagnostic instead of failing.
- Reports without `sessionSource` behave exactly as today (backward compatible).

**Session info envelope** (single endpoint: substitute sessionId into the template and GET, JSON):

```json
{
  "schemaVersion": 1,
  "sessionId": "0ab6…",
  "runtime": "claude-code",
  "runtimeVersion": "2.0.14",
  "agentKind": "main",
  "parentSessionId": null,
  "childSessionIds": ["agent-a1", "agent-b2"],
  "agentMeta": { "agentType": "general-purpose", "spawnDepth": 1 },
  "trajectory": { "format": "ndjson", "lineCount": 812, "content": "…" },
  "updatedAt": "2026-11-16T18:00:00+08:00"
}
```

- `runtime` is the closed AI agent type key, sharing the parser `runtime_key` vocabulary; it decides which adapter subclass interprets the envelope's key-value content.
- `agentMeta` is the runtime-specific key-value block: Claude Code uses the meta.json shape (agentType/spawnDepth/toolUseId/teamName, …); opencode uses the fields needed to project parent_id/modelID/providerID; each runtime owns one closed schema and the interpretation stays inside the subclass.
- `childSessionIds` returns one level of direct children only; traversal reuses the existing BFS with visited/depth/agent-count/time-budget limits, substituting into the template level by level.
- `trajectory.content` reuses the canonicalization rules of [11 §3.2](../../../plans/fullstack-design/11-bad-case-session-sync.md#32-接口-2单-agent-轨迹) (re-serialization, duplicate-key rejection, 64 MiB / 1 MiB-per-line / 1M-line limits); the implementation is extracted from `HttpSessionQuerySource` and shared.
- Validation: major `schemaVersion` mismatch → `SESSION_SOURCE_VERSION_INCOMPATIBLE`; `sessionId` echo mismatch → `SESSION_SOURCE_SESSION_MISMATCH`; when `agentKind=subagent`, `parentSessionId` must equal the traversal parent; v1 accepts only `trajectory.format="ndjson"`.

**Adapter factory**:

```text
apps/api/app/third_party_api/session_source/
  __init__.py       # auto-discover + register
  base.py           # BaseSessionSourceAdapter + SessionInfo + envelope model
  factory.py        # SessionSourceFactory
  claude_code.py    # ClaudeCodeSessionSourceAdapter
  <runtime>.py      # new agent adds only this file
```

- `BaseSessionSourceAdapter` is a template method: strict envelope validation and HTTP concerns (timeout, retries, process-wide serial lock, semantics aligned with 11 §3) live in the base class and a shared client; subclasses implement only `parse_agent_meta` and `project`, mapping runtime-specific key-value content onto the runtime-agnostic `SessionInfo` (runtime_key, agentKind, parentAgentId, childSessionIds, agent_meta, canonicalized trajectory).
- `@SessionSourceFactory.register` self-registers: duplicate `runtime_key` fails fast; unknown runtimes raise `UnsupportedTraceRuntime` (reusing the m9-06 semantics).
- An adapter's `runtime_key` must match a registered parser; `SessionInfo.runtime_key` is the selection key for `TraceParserFactory.create`, so runtime identity never gains a second home.
- A fake runtime subclass exercises the extension path in tests (aligned with the m9-06 fake parser test).

**Root-sync source selection and persistence**:

- `bad_cases` gains a `session_source` JSON NULL column; `bad_case_root_sync` gains `source_kind` (`report`/`global`, existing rows backfilled to `global`) and `source_snapshot` JSON NULL; dual-dialect migration.
- Selection rule: for one root take the non-null `session_source` with the newest `created_at` (ties break on the largest `bad_case_id` for determinism); roots without a per-report source fall back to the globally configured source and the existing two-endpoint path stays untouched.
- `source_snapshot` (runtime pre-declaration + URL template) is frozen at claim time so retries keep the same source; an explicit source failing marks the root failed (stable `SESSION_SOURCE_*` code) without silently degrading to the global source.
- `write_local_payloads` takes `runtime_key`/`agent_meta` from the `SessionInfo` projection: subagents can carry the real `parentAgentId` (and even `toolUseId`), improving the anchor precision of 11 §4.2; the main agent's `agent_meta` stores the envelope `agentMeta` (may be empty).

**Contracts and docs**: OpenAPI gains `BadCaseIngest.sessionSource`; run `pnpm contract:generate` then `contract:check`, with generated types never hand-edited; update 05 (§3.8 field, §10 per-report envelope subsection), 06 (bad_cases/bad_case_root_sync columns), 07 (session_source factory), and 11 (source selection); add one Agent Note covering the envelope contract and the steps to onboard a new runtime.

## Implementation steps

1. Failing tests first: ingest `sessionSource` validation (missing/duplicated placeholder, overlong, non-http(s), extra credential fields); envelope parsing (version mismatch, echo mismatch, unknown runtime, malformed NDJSON, `agentMeta` violating the subclass closed schema).
2. Implement the `third_party_api/session_source/` package: base class, factory, strict envelope model, and the Claude subclass; extract the shared trajectory canonicalization.
3. Dual-dialect migration: `bad_cases.session_source`, `bad_case_root_sync.source_kind/source_snapshot`, and backfills.
4. Root-sync source selection, snapshotting, and per-report traversal; verify `runtime_key` flows through replay.
5. Regenerate contracts; fake-runtime extension test; docs and the Agent Note.

## Dependencies and boundary

- Depends on: m9-06
- Non-goals: see below.

## Verification

```sh
pnpm test:api -- tests/m9-07-report-session-source
pnpm test:db
pnpm test:db:mysql
pnpm contract:check
pnpm verify:flow
```

- A report with `sessionSource` lands in storage, root-sync pulls via the template URL, the envelope `runtime` selects the adapter and parser, and `runtime_key`/`agent_meta` persist correctly.
- Reports without `sessionSource` fall back to the global source with today's behavior.
- A fake runtime registers only its subclass and root-sync picks it up without touching shared root-sync/normalize code.
- Unknown runtime / malformed envelope: the root is marked `failed`, `last_error` holds the stable code, and nothing enters the Claude parser.

## Acceptance

- The report contract stays backward compatible: old calls without `sessionSource` behave unchanged.
- The single envelope endpoint rebuilds the main/sub tree (childSessionIds recursion), and runtime_key flows through payload, source_records, and session_families.
- A new runtime only adds `session_source/<runtime>.py` and `parsers/<runtime>.py` plus registration.
- Unknown runtime, version mismatch, and echo mismatch map to stable error codes with no silent fallback.
- Contract, dual-dialect migration, flow, and docs gates stay green.

## Gates and CI

- API unit tests, dual-dialect database, contract, flow, and docs gates.

## Non-goals

- No full parsing for a second real runtime (e.g. opencode); only the extension point and a test fake.
- No changes to the catalog-sync (bad_case_query upstream) contract.
- No reporter credential fields and no authentication material persisted in the database.
- No incremental trajectory change detection or automatic re-pull.
- No frontend changes and no multi-instance cross-process locking.
