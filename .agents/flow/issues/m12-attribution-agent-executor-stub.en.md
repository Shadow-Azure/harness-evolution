# Agent-skill attribution executor seam and contract stub

English | [中文](m12-attribution-agent-executor-stub.md)

```yaml flow
kind: issue
id: m12-17
milestone: m12
depends:
  - m12-15
  - m12-16
priority: P0
status: done
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/config.py
  - apps/api/app/main.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 315
  url: https://github.com/Shadow-Azure/harness-evolution/issues/315
```

## Background

M10 established the pure `AttributionEngine` boundary, object-revision cache, and candidate writes, but the only executable implementation remains the fixed-rule `rule-v1`. The production intranet LLM, agent, and attribution skill are currently unavailable. Embedding a guessed intranet call in the runner would couple input assembly, skill resolution, remote execution, and report validation back into cache transactions and would leave CI without a deterministic way to verify the real-engine replacement seam.

## Goals

- Consume the m12-14 versioned report contract and m12-16 context input rather than creating parallel models.
- Add an attribution-executor protocol so an intranet adapter can be connected independently later.
- Provide a deterministic `agent-skill-stub-v1` engine that traverses the existing runner, cache, Probe Report, and candidate-link path.
- Keep `rule-v1` as the default and preserve existing public API behavior.

## Design authority

- [07 §5.12–5.14](../../../plans/fullstack-design/07-backend-implementation.md): potential matching, the pure attribution-engine boundary, and caching.
- [06 §4.2 and §5.8–5.9](../../../plans/fullstack-design/06-database-design.md): Probe Reports, cache keys, and candidate snapshots.
- [04 §5 and §8](../../../plans/fullstack-design/04-backend-architecture.md): external seams, jobs, and the executor expansion path.

## Implementation

- Consume the m12-15 `AttributionSkillResolver` and add an `AttributionExecutor` protocol; the stub executor accesses no network, file, or model.
- Make the input contract carry the selected target, bad case, target/report trigger coordinates, a minimal evidence list, skill reference, and context snapshot. Missing full trace is represented by an explicit warning rather than fabricated evidence.
- Make the output contract carry a schema version, conclusion, category, confidence, description, reasoning, evidence references, and warnings. Validate executor output before projecting it into the existing `AttributionResult`.
- Register the `agent-skill-stub-v1` engine key. The stub derives stable output only from its fixed input so cache, failure, and future adapter contract tests remain deterministic.
- Compute cache identity from the m12-14 execution manifest so engine, skill revision, model configuration, and context snapshot remain isolated.

## Implementation steps

1. Add failing tests for executor input/output, stub behavior, and engine registration errors.
2. Implement the protocols and `agent-skill-stub-v1` while keeping cache and persistence in the runner.
3. Add end-to-end service tests for fresh, reused, non-target, and failed stub executions.
4. Update design documentation and the Agent Note, then run API, type, contract, documentation, and Flow gates.

## Dependencies and boundary

- Depends on: m12-15 and m12-16.
- Boundary: deliver only the replaceable seam, versioned contracts, and deterministic stub; do not access intranet models or alter selected-target and PotentialMatcher semantics.

## Verification

```sh
pnpm test:api -- tests/test_attribution.py
pnpm typecheck:api
pnpm contract:check
pnpm verify:flow
```

- `agent-skill-stub-v1` returns stable output for identical input, and the second run reuses a cache entry isolated from `rule-v1`.
- An unknown resolver/executor or invalid output produces a diagnosable error and never writes a partial Probe Report.
- Default configuration still selects `rule-v1`; existing tests and public API contracts do not regress.

## Acceptance

- A future intranet adapter only implements and registers the executor protocol; it does not modify the runner, repository, or candidate state machine.
- Executor input distinguishes the selected attribution target from the bad-case reporting source and retains target/report trigger coordinates.
- Stub output passes structural validation and maps to the existing Probe Report fields; missing full trace produces a fixed warning.
- Executor timeout or failure follows the existing `blocked(attribution)` recovery path, and completed candidates are not recomputed.

## Gates and CI

- API unit tests, mypy, contracts, documentation, Flow, and existing dual-database gates.

## Non-goals

- Do not connect to an intranet LLM or agent service or read production credentials.
- Do not implement CRUD, binding UI, or a persistent revision repository for object-specific attribution skills.
- Do not persist full Session traces or extend the Probe Report database shape or public category enums.
- Do not describe the stub as a real attribution-quality implementation or make it the default engine.
