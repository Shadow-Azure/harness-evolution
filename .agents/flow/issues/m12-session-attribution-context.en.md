# Session attribution context assembly and evidence coordinates

English | [中文](m12-session-attribution-context.md)

```yaml flow
kind: issue
id: m12-09
milestone: m12
depends:
  - m10-02
  - m12-01
  - m12-07
priority: P0
status: backlog
scope:
  - apps/api/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 321
  url: https://github.com/Shadow-Azure/harness-evolution/issues/321
```

## Background

`PotentialMatcher` already finds associated Sessions and potential bad cases for a selected target revision, but the current attribution input carries only a bad-case summary, trigger coordinates, and limited metadata. A real agent needs the complete trace tree, every selected-target occurrence, the reporting node, and verifiable evidence. Fetching the whole tree once per bad case would amplify upstream latency and produce inconsistent snapshots within one Session.

## Goals

- Reuse the selected-target and Session-association results from `PotentialMatcher` without adding real-target routing.
- Build one hashable and redacted `AttributionContextBundle` per Session.
- Derive an independent executor input with verifiable evidence coordinates for each bad case in that Session.

## Design authority

- [07 §5.12](../../../plans/fullstack-design/07-backend-implementation.md): PotentialMatcher and target-occurrence semantics.
- [06 §7.4–7.5](../../../plans/fullstack-design/06-database-design.md): bad-case anchors, target entry points, and Session projection.
- [04 §5.2](../../../plans/fullstack-design/04-backend-architecture.md): raw-payload and normalization seams.

## Implementation

- Assemble the Session trace tree, every selected-target occurrence, all Session bad cases, reporting nodes, target-to-report paths, target definition, knowledge evidence, and prior reports.
- Return a stable context-snapshot hash, source versions, redaction result, and missing-data or degraded-relation warnings.
- Batch-read normalized facts first; fetch raw content on demand through the m12-01 upstream seam and release it after execution.
- Let each bad-case input reference the shared bundle and its own reporting node without copying or durably persisting the full trace.
- Keep the user-selected target authoritative; the model cannot replace `probe_object` in this stage.

## Implementation steps

1. Add fixtures for multiple occurrences, multiple bad cases, missing traces, unknown revisions, and degraded relations.
2. Implement the context provider, Session bundle, and per-case projection.
3. Add redaction, size limits, stable hashing, and evidence-coordinate validation.
4. Connect the runner batch-preparation stage and verify that it performs no N+1 fetches.

## Dependencies and boundary

- Depends on: m10-02, m12-01, and m12-07.
- Boundary: produce agent-consumable context input; do not execute a model, change potential policy, or automatically select another attribution target.

## Verification

```sh
pnpm test:api -- tests/session_attribution_context
pnpm performance:report -- --local
pnpm contract:check
```

- Multiple bad cases in one Session share one assembled bundle while retaining independent report nodes and evidence paths.
- Missing raw trace produces an explicit warning or blocked state rather than fabricated messages, tools, or target versions.

## Acceptance

- Input clearly separates the selected target, target occurrences, and bad-case reporting source.
- Every evidence reference resolves to a real node in the same context snapshot.
- Raw traces are not written to Probe Reports or durable business tables by default.

## Gates and CI

- API, performance, contract, redaction, documentation, and Flow gates.

## Non-goals

- Do not implement real-target discovery, model execution, skill registration, or attribution conclusions.
- Do not duplicate PotentialMatcher or alter exact target-revision matching semantics.
