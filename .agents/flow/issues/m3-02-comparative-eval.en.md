# Comparative evaluation and adoption decision

English | [中文](m3-02-comparative-eval.md)

```yaml flow
kind: issue
milestone: m3
priority: P1
status: backlog
scope:
  - research/**
  - apps/server/src/analysis/**
  - docs/charter.*
  - docs/metrics.*
  - .agents/notes/**
adr: []
github:
  number: 7
  url: https://github.com/Shadow-Azure/harness-evolution/issues/7
```

## Background

Without comparative evaluation, changes rely on intuition. Pin the baseline, task set and seed, then decide adoption by pre-declared thresholds.

## Goals

- Run baseline and treatment and record complete metrics.
- Recommend a decision from primary and guardrail metrics.
- Update the baseline on adoption and keep reproduction data on rejection.

## Acceptance

- Experiment records satisfy every field in charter and metrics.
- Decisions never depend on post-hoc threshold changes.
- Adoption and rejection both carry executable rollback instructions.
