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
  - m7
  - m8
  - m9
  - m10
  - m11
  - m12
  - m14
  - m15
```

## Vision

Harness Evolution connects traceable Claude Code sessions, reported problems, and attribution evidence to diagnose and improve coding agents. V2 makes workspaces the data and permission boundary and closes the loop between trace evidence, object attribution, and evolution runs.

## Milestone sequence

- **m1 Engineering foundation and quality gates**: FastAPI, Vue 3, dual-dialect storage, contracts, identity, jobs/SSE, and meta-gates.
- **m2 Trace data and normalization**: fixtures, local import, normalization, agent trees, idempotency, query APIs, and scheduling.
- **m3 Session browsing and execution flow**: list, overview, agent graph, deep links, and performance budgets.
- **m4 Problems and attribution**: V1 bad cases, probes, problem cards, error detail, and read-only attribution.
- **m5 Evolution loop**: targets, runs, six stages, events, git candidates, and placeholder evaluation.
- **m6 Real integration and delivery**: real upstream, contracts, execution, and clustering upgrades.
- **m7 Identity and workspace boundary**: one global admin, workspace roles, auth-provider seam, routing, and administration.
- **m8 Workspace data plane and overview**: ingest, quota, latest sessions, overview, and time filters.
- **m9 Session evidence and object revisions**: runtime identity, parser factory, relations, completion, revisions, and evidence coordinates.
- **m10 Attribution pipeline and seven-step evolution**: potential matching, cache, candidates, wizard, and run detail.
- **m11 Multi-attribution experience and V2 cutover**: lane DAG execution flow, multi-attribution detail, target overview, cross-stack verification, and retirement.
- **m12 Real integrations and algorithm delivery**: live upstream, contracts, patch/evaluation, clustering, and platform-quality debt.
- **m14 Problem-card display aligned with the prototype**: session cards lead with the description and carry type/object badges, the full case ID, and an association row.
- **m15 Production Claude Code operations**: the deploy pipeline installs Claude Code and injects model configuration without root or Node.js on the server.

## Delivery rules

- Every issue uses linked `plans/fullstack-design` sections as authority; the M9 evidence gate precedes M10 matching and attribution.
- Every issue passes repository gates and focused verification before merge.
- CI uses synthetic or sanitized fixtures; raw sessions, prompts, document bodies, and production credentials never enter the repository.
- Remote flow objects are closed rather than deleted; `pnpm flow:sync -- --retire-missing` is the only retirement path.
