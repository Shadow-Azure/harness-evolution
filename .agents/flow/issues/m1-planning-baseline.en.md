# M1 planning baseline and flow-tree initialization

English | [中文](m1-planning-baseline.md)

```yaml flow
kind: issue
milestone: m1
priority: P0
status: done
scope:
  - .agents/flow/**
  - .agents/notes/proposed/**
  - docs/roadmap.md
  - docs/roadmap.en.md
  - docs/roadmap.i18n.yaml
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 17
  url: https://github.com/Shadow-Azure/harness-evolution/issues/17
```

## Background

The repository previously installed flow gates but had no roadmap, milestone or issue instances. M1 must first fix the product path, four real session-family samples, cross-agent analysis boundary and acceptance order from findings to simulated evolution so implementation can begin from issues.

## Goals

- Initialize the roadmap and M1–M4 milestones.
- Create M1 issues for the frontend prototype, agent flow, unified findings, attribution and evolution simulation.
- Record decisions for session families, stable anchors and cross-agent analysis.

## Acceptance

- The product and flow roadmaps agree, and M1–M4 pass mechanical validation.
- M1 issues cover search and switching, execution flow, unified findings, attribution and evolution simulation.
- The Agent Note records rollout identity, session-family assembly and cross-agent analysis tradeoffs.
- `verify:flow`, `lint:docs` and `verify:docs` pass.
- GitHub milestone and issue numbers are backfilled so commit titles can cite them.
