# Real metadata compatibility and completion parsing

English | [中文](m9-02-trace-metadata-completion-parser.md)

```yaml flow
kind: issue
id: m9-02
milestone: m9
depends:
  - m9-01
priority: P0
status: backlog
scope:
  - apps/api/app/service/acquisition/**
  - apps/api/app/fixture_corpus.py
  - fixtures/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 237
  url: https://github.com/Shadow-Azure/harness-evolution/issues/237
```

## Background

Real metadata now contains new fields, while sessions may end on tool use.

## Goals

- Tolerate unknown metadata.
- Parse open tools and missing reports.
- Separate model identities.

## Design authority

- [15 §9.2、§9.4](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：revision 与完成状态。
- [07 §2.3–§2.5](../../../plans/fullstack-design/07-backend-implementation.md)：归一化与事务。

## Implementation

- Validate known keys and warn on others.
- Pair tool calls and results.
- Read task and stop state.

## Implementation steps

1. Add a sanitized failing fixture.
2. Implement parsing.
3. Test replay idempotency.

## Dependencies and boundary

- Dependencies: m9-01
- Boundary: no relation assembly.

## Verification

```sh
pnpm test:api -- tests/acquisition; pnpm data:normalize:sessions
```

- The fixture imports.
- Open tools are detected.
- Missing reports are detected.

## Acceptance

- Metadata drift is non-fatal.
- Completion differs from tool errors.

## Gates and CI

- API, data, fixture, and flow gates.

## Non-goals

- No raw message storage.
- No speculative inference.
