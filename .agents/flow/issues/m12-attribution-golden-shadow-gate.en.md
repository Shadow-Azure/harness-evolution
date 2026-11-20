# Attribution golden cases, shadow runs, and engine promotion gate

English | [中文](m12-attribution-golden-shadow-gate.md)

```yaml flow
kind: issue
id: m12-20
milestone: m12
depends:
  - m12-19
priority: P0
status: done
scope:
  - apps/api/**
  - fixtures/**
  - scripts/**
  - package.json
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 316
  url: https://github.com/Shadow-Azure/harness-evolution/issues/316
```

## Background

Agent-skill attribution feeds clustering, proposals, and real patch execution, so valid JSON alone does not establish reliable target conclusions or evidence. A redacted and reproducible quality baseline is required before and after the intranet executor becomes available, and no new engine or skill revision may replace the production default without comparison.

## Goals

- Build golden cases that cover core attribution semantics and failure modes.
- Compare rule, stub, default-skill, and target-specific-skill behavior offline and in shadow runs.
- Define promotion, blocking, and rollback gates for engines and skill revisions.

## Design authority

- [09 R2 and R11](../../../plans/fullstack-design/README.md): multi-attribution cache and real-execution risks.
- [07 §5.13](../../../plans/fullstack-design/07-backend-implementation.md): attribution conclusions, confidence, and runner behavior.
- [01 §4.3](../../../plans/fullstack-design/01-architecture.md): the evolution loop and evidence boundary.

## Implementation

Register the offline Golden evaluator as `pnpm attribution:evaluate` in the root package manifest.

- Add redacted fixtures for self/discovery, target occurrence without causation, multiple occurrences, multiple targets, missing traces, degraded relations, non-skill faults, and prompt injection.
- Define metrics for conclusion accuracy, evidence validity, introduction/detection-point accuracy, schema compliance, latency, tokens, and failures.
- Make shadow execution write isolated execution/results without changing official Probe Reports, candidates, clusters, or cache hits.
- Provide human comparison and accept/reject records; only threshold-passing engines or skill revisions become production-eligible.
- Preserve one-step rollback to the prior valid skill revision or `rule-v1`.

## Implementation steps

1. Define the golden-case schema, redaction rules, metrics, and promotion thresholds.
2. Build fixtures and an offline evaluator, first proving deterministic rule/stub behavior.
3. Implement shadow runs and diff reports outside the official attribution chain.
4. Connect promotion state, human judgment, and rollback evidence.

## Dependencies and boundary

- Depends on: m12-19.
- Boundary: evaluate attribution-engine and skill quality and control promotion; do not train a model or automatically edit skills.

## Verification

```sh
pnpm test:api -- tests/attribution_eval
pnpm fixtures:check
pnpm test:gates
```

- A fixed engine and skill revision produce reproducible metrics on the same golden set.
- Shadow runs do not alter official reports, candidates, clusters, or run state.

## Acceptance

- An engine or skill revision that misses thresholds cannot become the production default.
- Every promotion and rollback traces to the evaluation set, metrics, execution manifest, and human decision.
- Prompt injection, fabricated evidence, and missing context have explicit negative cases.

## Gates and CI

- API, fixture, evaluation-determinism, security, documentation, and Flow gates.

## Non-goals

- Do not train or fine-tune models, automatically publish skills, or generate real patches.
- Do not place raw production user traces in repository fixtures.
