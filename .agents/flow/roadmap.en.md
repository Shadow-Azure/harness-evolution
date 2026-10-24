# Roadmap

English | [中文](roadmap.md)

```yaml flow
kind: roadmap
milestones:
  - m1
  - m2
  - m3
  - m4
  - m5
  - m6
```

## Vision

Harness Evolution turns linked Claude Code traces, external problems, and attribution data into diagnosable, evolvable coding-agent improvements. Delivery follows the SaaS boundary in `plans/fullstack-design`; the timeline page remains retired.

## Milestone sequence

- **m1 Engineering baseline and quality gates:** FastAPI, Vue 3, dual-dialect storage, contracts, auth, jobs/SSE, and CI meta-gates.
- **m2 Trace data and normalization:** fixtures, local real-data import, parsing, agent trees, idempotency, session APIs, and scheduling.
- **m3 Session browsing and execution flow:** list, overview, agent execution graph, deep links, and performance budgets.
- **m4 Problems and attribution:** external read-only bad_case/probe data through API, graph cards, and error details.
- **m5 Evolution loop:** targets, runs, six steps, events, real git candidates, and placeholder patch/eval automation.
- **m6 Real integrations:** real upstream, external contracts, real patch/evaluation, and clustering upgrade.

## Delivery rules

- Every issue treats its linked `plans/fullstack-design` sections as the technical authority; issues define slices, steps, verification, and boundaries.
- Every issue runs repository static gates plus focused verification; every new gate has a self-test and route entry.
- CI uses synthetic fixtures; `claude-code-sessions/` and `data/` remain local and never enter Git or issue bodies.
- Remote flow objects are closed, never deleted; `pnpm flow:sync -- --retire-missing` is the sole retirement entry.
