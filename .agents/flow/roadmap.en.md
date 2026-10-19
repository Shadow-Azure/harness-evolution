# Roadmap

English | [中文](roadmap.md)

```yaml flow
kind: roadmap
milestones:
  - m1
  - m2
  - m3
  - m4
```

## M0 Engineering scaffold (done)

The web and server workspace, shared contracts and health check are wired.

## M1 Frontend experience prototype: session family and agent collaboration (current)

Validate the final information architecture with four real root session families. The root agent and every descendant subagent share one execution-flow diagram; root and child-agent findings appear together in one findings panel and are attributable to a specific skill or agent. Findings, attribution and evolution data are stubbed, and the prototype uses local snapshots without SQLite or the API. See [m1](milestones/m1-prototype.en.md).

Acceptance: without switching agents, one findings list shows every root and child-agent problem; attribute from the diagram or list, select a target skill or agent, aggregate that target's findings, run simulated evolution/training and validation, then accept or reject based on metrics.

## M2 Real trace service: session family import and storage

Stream rollouts, assemble families by parent_thread_id, implement idempotent import, SQLite repositories and REST APIs, then replace prototype snapshots with real data. See [m2](milestones/m2-trace-service.en.md).

Acceptance: importing the four root families repeatedly creates no duplicates, and the web app matches the prototype.

## M3 AI trace diagnosis: cross-agent evidence links

Rule and AI diagnosis both scope to a session family. Analyze each agent first, then let the root agent merge, deduplicate and produce cross-agent conclusions. See [m3](milestones/m3-ai-diagnosis.en.md).

Acceptance: one root analysis covers every descendant subagent, and each finding locates its agent path, rollout and event.

## M4 Evolution loop: skill and agent improvement evaluation

Aggregate attributed findings by skill or agent, generate minimal-change proposals, and record comparative evaluation plus adoption or rollback. See [m4](milestones/m4-evolution-loop.en.md).

Acceptance: at least one real problem completes "diagnosis → proposal → comparative verification → adopt or reject".
