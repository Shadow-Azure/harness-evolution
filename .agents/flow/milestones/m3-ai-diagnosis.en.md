# M3 AI trace diagnosis: cross-agent evidence links

English | [中文](m3-ai-diagnosis.md)

```yaml flow
kind: milestone
id: m3
title: M3 AI 轨迹诊断：跨 Agent 证据回链
status: planned
github:
  number: 7
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/7
```

## Goal

Make root-session analysis cover every descendant subagent and produce verifiable, navigable findings.

## Scope

- Rule and AI diagnosis both scope to a session family
- Extract candidate findings per agent, then merge, deduplicate and synthesize across agents at the root
- Analysis job state, history, structured output and evidence validation
- Categories for agent orchestration, skill use, tool execution, verification closure and cost anomalies

## Acceptance

- One root analysis includes every descendant subagent
- Every finding states its scope, agent path, evidence and improvement suggestion
- Duplicate cross-agent issues collapse into one primary finding with related agents listed
- Evidence anchors include rollout, line and item or call id, and navigate exactly
- Large tool outputs and images never enter model context verbatim

## Non-goals

- Automatically modifying skills or agents
- Automatic merges, releases or permission changes
