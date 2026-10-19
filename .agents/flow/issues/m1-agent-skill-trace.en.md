# Agent execution-flow diagram and skill usage tracing

English | [中文](m1-agent-skill-trace.md)

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
  number: 8
  url: https://github.com/Shadow-Azure/harness-evolution/issues/8
```

## Background

Analyzing the root agent must include every child subagent. A tree list alone does not explain execution order, so the root and all children need one interactive execution-flow diagram. Rollouts have no first-class SkillInvocation event; skill use mainly appears as reads of `SKILL.md` followed by tool calls, so derived events must retain their evidence.

## Goals

- Build an execution-flow diagram for the root agent and every child, showing depth, agent path, nickname and state.
- Use directed edges for spawn, wait, send, followup, interrupt and return relationships.
- Show turn, tool-call, failure and finding counts on each node.
- Derive SkillUse from `SKILL.md` reads with name, count, path and evidence.
- Switch the timeline from a node and open that agent's findings directly.

## Acceptance

- The four-level execution-flow diagram in the 20:05 family expands completely.
- Every descendant across the four root sessions appears exactly once.
- Collaboration edges trace from the root to any child and expose wait and return relationships.
- Clicking a child node opens its trace, finding count and finding list.
- The multiple skills in 17:32 and repeated skill loads in 08:46 are recognized.
- Selecting an agent filters the timeline and preserves a route back to the root.
