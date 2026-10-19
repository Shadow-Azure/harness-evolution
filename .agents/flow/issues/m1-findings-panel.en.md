# Family-level findings panel and evidence navigation

English | [中文](m1-findings-panel.md)

```yaml flow
kind: issue
milestone: m1
priority: P0
status: backlog
scope:
  - apps/web/src/**
  - packages/contracts/**
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 12
  url: https://github.com/Shadow-Azure/harness-evolution/issues/12
```

## Background

The prototype's core question is what went wrong in a session. Root and every subagent finding must appear in one list so users see the whole picture without switching agents; the prototype uses reviewed diagnosis snapshots clearly labeled as non-live AI results.

## Goals

- Show root and every child-agent finding in one list on the right.
- Label each finding's source agent and allow per-agent filtering without splitting the data source.
- Filter by severity, category and agent.
- Give every finding a conclusion, evidence and improvement suggestion.
- Open attribution details from a finding and continue into evolution simulation.
- Navigate and highlight the exact rollout, agent, turn and event.

## Acceptance

- Each of the four root sessions has a demonstrable diagnosis snapshot.
- The initial view includes root and child-agent findings with no source switch.
- Every finding carries a source-agent label and can be filtered by agent.
- Cross-agent issues appear once and expand into evidence from related child agents.
- Every child-agent example finding opens from either the flow diagram or findings panel.
- Findings distinguish agent orchestration, skill use, tool failure and verification gaps.
- Every finding opens its attribution detail with no broken demo path.
- Evidence navigation remains accurate in long traces.
- The page labels results as example snapshots rather than live model analysis.
