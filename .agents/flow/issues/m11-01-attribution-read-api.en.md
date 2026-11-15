# Paged attribution reads and stable deep-link APIs

English | [中文](m11-01-attribution-read-api.md)

```yaml flow
kind: issue
id: m11-01
milestone: m11
depends:
  - m10-03
priority: P0
status: backlog
scope:
  - apps/api/app/api/problems.py
  - apps/api/app/service/bad_cases/**
  - apps/api/app/db/crud/**
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 216
  url: https://github.com/Shadow-Azure/harness-evolution/issues/216
```

## Background

Error detail needs paged revision-scoped attributions and stable item deep links.

## Goals

- Return counts and pages.
- Validate case ownership.
- Keep probe compatibility.

## Design authority

- [05 §3.9、§4.19](../../../plans/fullstack-design/05-api-design.md)：归因 DTO 与端点。
- [06 §4.3](../../../plans/fullstack-design/06-database-design.md)：归因读取口径。

## Implementation

- Use stable ordering.
- Hide cross-case items.
- Expose trigger comparison.

## Implementation steps

1. Write read tests.
2. Implement DTOs.
3. Update contracts.

## Dependencies and boundary

- Dependencies: m10-03
- Boundary: no UI.

## Verification

```sh
pnpm test:api -- tests/problems tests/attribution; pnpm contract:check
```

- Paging is stable.
- Cross-case items fail.
- Legacy probes remain readable.

## Acceptance

- Items include revision and run.
- Warnings are visible.

## Gates and CI

- API, contract, and flow gates.

## Non-goals

- No manual single-item attribution.
- No probe-first product model.
