# Improvement proposal generation and attribution

English | [中文](m3-01-improvement-proposal.md)

```yaml flow
kind: issue
milestone: m3
priority: P0
status: backlog
scope:
  - apps/server/src/analysis/**
  - packages/contracts/**
  - research/**
  - docs/charter.*
  - docs/metrics.*
  - .agents/notes/**
adr: []
github:
  number: 6
  url: https://github.com/Shadow-Azure/harness-evolution/issues/6
```

## Background

A diagnosed problem only becomes valuable as a minimal change. A proposal must state its attribution layer, expected impact and rollback path.

## Goals

- Attribute problems to skill / prompt / tools / control flow.
- Generate a minimal-change proposal and verification plan.
- Reference baseline, task set and decision rule in the proposal.

## Acceptance

- At least one real problem yields a reviewable proposal.
- The proposal covers constraints, candidates, rationale and rollback.
- The proposal never changes the evaluator and harness in the same variable.
