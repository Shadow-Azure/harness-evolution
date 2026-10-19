# Session explorer and family summary

English | [中文](m1-session-explorer.md)

```yaml flow
kind: issue
milestone: m1
priority: P0
status: backlog
scope:
  - apps/web/src/**
  - apps/web/package.json
  - pnpm-lock.yaml
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 14
  url: https://github.com/Shadow-Azure/harness-evolution/issues/14
```

## Background

The prototype must first expose the family size, task state and finding density of four complex sessions. The top-level list shows root sessions only, leaving subagents inside detail, so collaboration traces are not mistaken for independent conversations.

## Goals

- Build the left-hand session explorer and family summary cards.
- Show aggregate turn, agent, command, failure, skill and finding counts.
- Support filtering by repository, time, status and finding density.
- Persist the selected root session, agent and evidence position in the URL.

## Acceptance

- The top level shows only four root sessions with descendant agent counts.
- Each summary distinguishes the 20:05, 17:32, 08:46 and 12:34 scenarios.
- Search and filters locate a target session within one screen.
- Reloading restores the root session, agent and evidence position.
- Empty, unselected and failed-load states are explicit.
