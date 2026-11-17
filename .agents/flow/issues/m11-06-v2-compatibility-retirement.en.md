# V2 documentation, compatibility, and retirement

English | [中文](m11-06-v2-compatibility-retirement.md)

```yaml flow
kind: issue
id: m11-06
milestone: m11
depends:
  - m11-05
priority: P1
status: in-progress
scope:
  - docs/**
  - plans/**
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 221
  url: https://github.com/Shadow-Azure/harness-evolution/issues/221
```

## Background

After V2 lands, permanent docs and compatibility boundaries must describe reality.

## Goals

- Update architecture and development facts.
- Define retirement conditions.
- Synchronize design notes.

## Design authority

- [15 §7–§9](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：实施与兼容边界。
- [README 与仓库现状](../../../plans/fullstack-design/README.md)：文档同步要求。

## Implementation

- Document legacy endpoint removal triggers.
- Update bilingual docs.
- Record evidence and knowledge triggers.

## Implementation steps

1. Audit endpoints and tables.
2. Update docs and notes.
3. Run docs and flow gates.

## Dependencies and boundary

- Dependencies: m11-05
- Boundary: no premature endpoint deletion.

## Verification

```sh
pnpm record:i18n -- docs/architecture.md; pnpm verify:docs; pnpm verify:flow
```

- No stale V1 claims remain.
- Retirement is testable.
- Pairing is current.

## Acceptance

- One fact has one home.
- Compatibility removal has a checklist.

## Gates and CI

- Documentation, flow, and release gates.

## Non-goals

- No deletion during compatibility.
- No future plan stated as current fact.
