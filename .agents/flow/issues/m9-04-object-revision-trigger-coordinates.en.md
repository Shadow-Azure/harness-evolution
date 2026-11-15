# Object revision resolution, trigger coordinates, and replay

English | [中文](m9-04-object-revision-trigger-coordinates.md)

```yaml flow
kind: issue
id: m9-04
milestone: m9
depends:
  - m9-02
  - m9-03
priority: P0
status: backlog
scope:
  - apps/api/app/service/acquisition/**
  - apps/api/app/db/**
  - apps/api/alembic/**
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 239
  url: https://github.com/Shadow-Azure/harness-evolution/issues/239
```

## Background

Real skill listings can expose digests but no semantic versions.

## Goals

- Support tag, digest, and unknown revisions.
- Persist stable trigger coordinates.
- Replay with a parser version bump.

## Design authority

- [15 §9.2–§9.3](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：revision 与触发规则。
- [06 §7.5](../../../plans/fullstack-design/06-database-design.md)：对象进入点与比较。

## Implementation

- Parse skill-listing digests.
- Separate explicit skill events from message attribution.
- Prefer timestamps and fallback to coordinates.

## Implementation steps

1. Write revision tests.
2. Implement coordinates and replay.
3. Verify unknown remains unknown.

## Dependencies and boundary

- Dependencies: m9-02, m9-03
- Boundary: no matcher.

## Verification

```sh
pnpm test:api -- tests/acquisition; pnpm data:replay:sessions; pnpm test:db
```

- Digests match across sessions.
- Unknown is explicit.
- Cross-agent order is stable.

## Acceptance

- Identity no longer requires semantic versions.
- Unknown reasons are visible.

## Gates and CI

- API, database, replay, and flow gates.

## Non-goals

- No name-only matching.
- No full skill storage.
