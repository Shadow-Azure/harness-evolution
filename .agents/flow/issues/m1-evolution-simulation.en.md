# Evolution simulation and validation-metric decisions

English | [中文](m1-evolution-simulation.md)

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
  number: 11
  url: https://github.com/Shadow-Azure/harness-evolution/issues/11
```

## Background

Attribution must become a comparable improvement proposal. Evolution starts from a skill or agent, aggregates the findings attributed to that target, then generates a change and calls the validation platform. M1 assumes the platform returns metrics; the UI presents the run and lets the user accept or reject. The prototype simulates the interface, training/improvement and data without performing real changes.

## Goals

- Define contracts for EvolutionTarget, EvolutionProposal, ValidationRun, MetricComparison and EvolutionDecision.
- Select a target skill or agent first and automatically aggregate the findings attributed to it.
- Launch evolution simulation from the target page with queued, training/improvement, validation and completed states.
- Show the change description, target finding, baseline versus candidate metrics and guardrails.
- Provide accept and reject actions with local decision state.
- Use a replaceable mock adapter for the validation-platform interface.

## Acceptance

- Evolution requires selecting a skill or agent and shows that target's finding set.
- A target with no attributed findings cannot start, and findings from other targets never leak into the run.
- The page shows target type, target name, finding count and an evidence entry for every finding.
- Starting shows validation progress, candidate changes and before/after metrics.
- Metrics cover task success rate, regressions, cost and latency with explicit thresholds.
- Simulated results include at least one recommended acceptance and one recommended rejection.
- Accept or reject state persists for the current prototype session and can be reset.
- The page labels the simulated validation platform and makes no external call or code change.
