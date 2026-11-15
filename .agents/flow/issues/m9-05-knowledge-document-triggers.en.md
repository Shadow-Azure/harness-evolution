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
status: backlog
scope:
  - apps/api/app/service/acquisition/**
  - apps/api/app/db/**
  - apps/api/app/api/**
  - packages/contracts/**
  - fixtures/**
  - tests/**
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

- Add knowledge event and object types together.
- Require a configured knowledge root.
- Use provider adapters.

## Implementation steps

1. Write paired source/knowledge read tests.
2. Implement config and adapters.
3. Add revision evidence.

## Dependencies and boundary

- Dependencies: m9-01, m9-02, m9-04
- Boundary: evidence first, evolution later.

## Verification

```sh
pnpm test:api -- tests/acquisition tests/knowledge; pnpm contract:check
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
