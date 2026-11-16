# Knowledge-document trigger extraction

English | [中文](m9-05-knowledge-document-triggers.md)

```yaml flow
kind: issue
id: m9-05
milestone: m9
depends:
  - m9-01
  - m9-02
  - m9-04
priority: P0
status: in-progress
scope:
  - apps/api/alembic/**
  - apps/api/app/service/acquisition/**
  - apps/api/app/service/sessions/**
  - apps/api/app/service/workspaces/**
  - apps/api/app/db/**
  - apps/api/app/api/**
  - apps/api/app/utils/**
  - apps/api/app/errors.py
  - packages/contracts/**
  - fixtures/**
  - tests/**
  - apps/api/tests/**
  - apps/web/src/api/**
  - apps/web/src/pages/workspaces/**
  - plans/fullstack-design/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 240
  url: https://github.com/Shadow-Azure/harness-evolution/issues/240
```

## Background

Only Skill, Agent, and Workflow calls are normalized today; knowledge reads and retrievals are invisible.

## Goals

- Recognize configured documents.
- Persist document identity and coordinates.
- Exclude ordinary source reads.

## Design authority

- [15 §9.3](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：知识库触发边界。
- [06 §3.4、§7.5](../../../plans/fullstack-design/06-database-design.md)：事件与对象进入点。

## Implementation

- Migration 0019 adds document id/revision/path/retrieval kind/scope columns and an `(agent_id, kind, document_id)` index to `agent_events`, plus the `workspaces.knowledge_roots` JSON configuration. Knowledge events do not extend `bad_cases.object_type` / `evolution_targets.object_type`.
- Only a Read inside a configured knowledge root becomes `kind=knowledge`; Edit/Bash never do.
- MCP knowledge tools are recognized through an explicit adapter whitelist; only id/revision/path/kind/scope/hash are stored, never bodies, chunks, or raw responses.
- The Session API exposes knowledge events and document evidence; parser 4 → 5 replays claude-code history.

## Implementation steps

1. Write paired source/knowledge read tests.
2. Implement config and adapters.
3. Add revision evidence.

## Dependencies and boundary

- Dependencies: m9-01, m9-02, m9-04
- Boundary: evidence first, evolution later.

## Verification

```sh
pnpm test:api -- tests/m9-05-knowledge-document-triggers; pnpm contract:check
```

- Knowledge reads emit events.
- Source reads do not.
- Multi-document results are stable.

## Acceptance

- All three trigger kinds share coordinates.
- No full document content is stored.

## Gates and CI

- API, contract, fixture, privacy, and flow gates.

## Non-goals

- No document body storage.
- No knowledge patching.
