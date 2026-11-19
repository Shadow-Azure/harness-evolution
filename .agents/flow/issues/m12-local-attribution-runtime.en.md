# Run local attribution Skills per bad case and persist canonical reports

English | [中文](m12-local-attribution-runtime.md)

```yaml flow
kind: issue
id: m12-26
milestone: m12
depends:
  - m12-23
priority: P0
status: done
scope:
  - scripts/flow-sync.mjs
  - apps/api/**
  - apps/web/**
  - attribute-badcases/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 387
  url: https://github.com/Shadow-Azure/harness-evolution/issues/387
```

## Background

Package activation and object bindings must select executable instructions for each new run.

## Goals

Produce a canonical report for every included candidate with the configured agent and model.

## Design authority

[Execution and persistence](../../../plans/fullstack-design/07-backend-implementation.md)

## Implementation

Snapshot the selected package, materialize evidence and object prompts, invoke the agent, validate script output, then commit the report and candidate link.

## Implementation steps

1. Integrate main.
2. Connect Skill resolution and execution.
3. Verify SQLite persistence and retries.

## Dependencies and boundary

Reuse #374 package administration and #315 executor boundaries.

## Verification

Run `pnpm test:api -- tests/attribution/test_local_runtime.py` against a temporary SQLite database. The synthetic case produces one canonical report, links it in SQLite and reuses it on replay.

## Acceptance

Object binding wins over workspace and built-in defaults. Flow and context survive reporting and clustering. Invalid output cannot enter storage.

## Gates and CI

API tests, type checking and contract generation.

## Non-goals

Existing historical runs retain their recorded executor.
