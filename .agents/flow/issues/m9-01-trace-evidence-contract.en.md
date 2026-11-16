# Trace evidence contract, relation confidence, and completion-state migration

English | [中文](m9-01-trace-evidence-contract.md)

```yaml flow
kind: issue
id: m9-01
milestone: m9
depends:
  - m9-06
priority: P0
status: in-progress
scope:
  - apps/api/app/db/**
  - apps/api/app/service/sessions/**
  - apps/api/alembic/**
  - apps/api/tests/**
  - apps/web/src/**
  - packages/contracts/**
  - plans/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 236
  url: https://github.com/Shadow-Azure/harness-evolution/issues/236
```

## Background

Current tree state cannot express open tool calls, missing child reports, or external attempt failures, and relations are only linked/unlinked. M9-06 establishes runtime identity and the parser factory, but no shared fields yet carry execution_outcome, relation_confidence, object revisions, agent/skill definition fingerprints, or file-read evidence.

## Goals

- Add execution_outcome, end_reason, relation_confidence, and related evidence fields.
- Add object_revision, runtime_version, agent_definition_hash, skill_definition_hash, and model evidence.
- Add file-read evidence: path, range, complete, and content hash without storing bodies.
- Keep parser_version, runtime_version, and definition fingerprints separate.

## Design authority

- [15 §9.1–§9.4](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md#91-父子关系证据): relations, revisions, triggers, and completion.
- [06 §3.0.1 Runtime identity](../../../plans/fullstack-design/06-database-design.md#301-runtime-身份与-parser-版本): runtime_key and per-runtime parser_version.
- [06 §3.3–§3.4, §9](../../../plans/fullstack-design/06-database-design.md): trace table evolution.

## Implementation

- Extend stable fields on agents/session_families/agent_events: execution_outcome, end_reason, relation_confidence, object_revision, definition_hash, file_read_hash, read_complete.
- Store execution completion on session_families without overwriting parse health.
- Define closed API enums and migration backfills; legacy rows become legacy_unknown.
- runtime_key comes from m9-06; this issue does not create another runtime table.

## Implementation steps

1. Write failing migration and session DTO tests for both dialects.
2. Implement columns, indexes, defaults, and backfills.
3. Update OpenAPI, contract snapshots, and evidence DTOs.
4. Add legacy-backfill and unknown-state tests.

## Dependencies and boundary

- Dependency: m9-06
- Boundary: establish data contracts and DTOs only; do not parse new evidence.

## Verification

```sh
pnpm test:db; pnpm test:db:mysql; pnpm contract:check
```

- Legacy rows backfill as legacy_unknown.
- Definition/file hashes are nullable with the designed nullability.
- Both dialects upgrade twice.
- runtime_key and parser_version coexist without overwriting each other.

## Acceptance

- Evidence represents parse health, execution closure, object definitions, and file reads.
- Contracts contain no free-text states.
- Messages, tool output, and definition bodies are not stored.

## Gates and CI

- Database, contract, and flow gates.

## Non-goals

- No revision inference.
- No attribution schema changes.
- No parser or second-runtime implementation.
