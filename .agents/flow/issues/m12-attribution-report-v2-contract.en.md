# Attribution report V2 contract, execution manifest, and cache semantics

English | [中文](m12-attribution-report-v2-contract.md)

```yaml flow
kind: issue
id: m12-07
milestone: m12
depends:
  - m10-03
  - m11-01
priority: P0
status: backlog
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 317
  url: https://github.com/Shadow-Azure/harness-evolution/issues/317
```

## Background

The current `probe_reports` shape carries only `attributed|non_target`, three `attribute_type` values, and two text blocks, while its cache key covers only workspace, bad case, target, revision, policy, and engine. Pluggable agent-skill attribution also needs structured evidence, introduction and detection points, skill/model/context versions, and per-attempt status. Without one report contract first, the skill, executor, UI, and clustering slices would invent incompatible fields and reuse stale cache entries.

## Goals

- Keep `probe_reports` as the single attribution-report source of truth and define a backward-compatible structured V2 report.
- Separate execution status, attribution conclusion, classification, evidence, and execution-manifest semantics.
- Include every skill, model, context, and schema version that affects a conclusion in cache identity.

## Design authority

- [06 §4.2 and §5.8](../../../plans/fullstack-design/06-database-design.md): multi-attribution, Probe Reports, and cache semantics.
- [07 §5.13](../../../plans/fullstack-design/07-backend-implementation.md): attribution engine and runner boundaries.
- [05 §3.9 and §4.19](../../../plans/fullstack-design/05-api-design.md): public attribution contracts and read APIs.

## Implementation

- Define `report_schema_version` and a structured payload containing the selected target, conclusion, classification dimension, introduction point, detection point, evidence, analysis, proposal hint, and warnings.
- Keep `attributed|non_target|inconclusive` separate from execution states such as queued/running/succeeded/blocked/failed; final enums follow the design review.
- Add an immutable execution manifest containing engine, skill revision/content hash, model-config fingerprint, context-snapshot hash, and output schema.
- Replace the cache identity with a canonical execution-manifest hash while preserving legacy seven-part cache reads.
- Evaluate and implement an `attribution_executions` audit table that records attempts without becoming a parallel report table.

## Implementation steps

1. Write report-schema, conclusion/state truth-table, and cache-invalidation tests.
2. Update migrations, repositories, OpenAPI, and generated types.
3. Update attribution read APIs and graceful UI handling for unknown or inconclusive fields.
4. Add SQLite/MySQL, legacy-migration, and concurrent-cache tests.

## Dependencies and boundary

- Depends on: m10-03 and m11-01.
- Boundary: define and persist the report, execution manifest, and cache facts; do not call an LLM or implement skill registration or full-trace context.

## Verification

```sh
pnpm test:api -- tests/attribution
pnpm test:db
pnpm test:db:mysql
pnpm contract:check
```

- Changing the skill, model, context, or schema produces a different cache identity.
- Legacy reports remain readable and V2 structured fields serialize and deserialize deterministically.

## Acceptance

- One bad case and target revision retain one current valid V2 report with a traceable execution manifest.
- Execution failure is never stored as `non_target`, and insufficient evidence is never fabricated into a certain conclusion.
- Every cache hit explains the skill, model, and context versions it reused.

## Gates and CI

- API, dual-database migration, contract, documentation, and Flow gates.

## Non-goals

- Do not create a second attribution-report primary table or public identifier.
- Do not persist complete raw Session traces.
- Do not implement the intranet model adapter, skill editor, or clustering algorithm.
