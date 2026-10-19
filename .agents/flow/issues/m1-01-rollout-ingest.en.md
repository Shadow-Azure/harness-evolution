# Codex rollout scanning and incremental ingest

English | [中文](m1-01-rollout-ingest.md)

```yaml flow
kind: issue
milestone: m1
priority: P0
status: backlog
scope:
  - apps/server/src/ingest/**
  - apps/server/src/storage/**
  - packages/contracts/**
  - docs/architecture.*
  - .agents/notes/**
adr: []
github:
  number: 2
  url: https://github.com/Shadow-Azure/harness-evolution/issues/2
```

## Background

Without ingestion, neither the web app nor diagnosis has a real data source. Codex rollouts are JSONL and need replayable parsing plus idempotent storage.

## Goals

- Scan the local Codex session directory and detect new rollouts.
- Parse raw records and normalize them into session / turn / item.
- Write idempotently through the SQLite repository while retaining raw records.

## Acceptance

- Re-importing the same rollout creates no duplicate data.
- Parse failures report a clear error and the original line location.
- Parsing and idempotency have automated test coverage.
