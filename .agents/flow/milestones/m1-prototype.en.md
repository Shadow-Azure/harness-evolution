# M1 Frontend experience prototype: session family and agent collaboration

English | [中文](m1-prototype.md)

```yaml flow
kind: milestone
id: m1
title: M1 前端体验原型：Session Family 与 Agent 协作
status: active
github:
  number: 5
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/5
```

## Goal

Validate the final information architecture with real, complex traces before investing in the database and model calls.

## Scope

- Four root session families: 20:05:12, 17:32:52, 08:46:41 and 12:34:14
- Search and switch sessions, then enter the full execution flow from a family summary
- One execution-flow diagram for the root agent and every descendant, retaining parentage, agent paths and state
- Turn timeline, skill usage and stubbed family-level findings
- Root and child-agent findings share one list and are attributable to a specific skill or agent
- Finding attribution page: problem, impact, cause, inference steps, evidence and target
- Evolution simulation page: choose a target skill or agent, aggregate its findings and simulate training/improvement plus validation
- Local snapshot adapter; no SQLite, production API or model calls

## Acceptance

- 64 rollouts index and load lazily: 25,170 records and roughly 72.2MB of raw payload
- Search, filter and switch among the four sessions; reload restores the selection
- The execution-flow diagram covers every descendant through level four and navigates to any node
- Repeated loads of the same skill are visible and link back to their tool calls
- One findings list shows every root and child-agent problem without switching agents
- Every finding labels its source agent and opens evidence from either the diagram or list
- Every finding is attributed to a skill or agent with its target, evidence and inference path
- Evolution first selects a target skill or agent, aggregates its findings, then simulates training/improvement and validation
- Metrics drive an accept or reject decision whose state persists
- Long turns, large tool outputs, images and MCP results do not block first paint
- Raw JSONL stays out of the repository; only redacted or derived fixtures are committed

## Non-goals

- SQLite, incremental import or REST APIs
- Live model analysis
- The real validation platform, real code changes, automatic merges or model-weight training
