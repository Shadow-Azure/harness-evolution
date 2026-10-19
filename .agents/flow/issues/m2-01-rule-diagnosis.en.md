# Rule diagnosis and evidence location

English | [中文](m2-01-rule-diagnosis.md)

```yaml flow
kind: issue
milestone: m2
priority: P0
status: backlog
scope:
  - apps/server/src/analysis/**
  - packages/contracts/**
  - docs/architecture.*
  - .agents/notes/**
adr: []
github:
  number: null
  url: null
```

## Background

Reading traces turn by turn is expensive. Start with mechanically detectable problems: tool failures, repeated retries, unverified edits and unclosed errors.

## Goals

- Define shared contracts for findings, evidence and severity.
- Implement rule diagnosis and persist analysis jobs.
- Attach a jumpable evidence location to every finding.

## Acceptance

- Fixed fixture traces produce a stable findings list.
- Rule hits and misses have test coverage.
- Diagnosis results are readable through the API.
