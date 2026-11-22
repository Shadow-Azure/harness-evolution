# Attribution confidence becomes an evidence-completeness rule score

English | [中文](bugfix-attribution-rule-confidence.md)

```yaml flow
kind: issue
id: bugfix-18
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - apps/api/app/db/crud/attributions.py
  - apps/api/app/db/crud/bad_cases.py
  - apps/api/app/service/**
  - apps/api/tests/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 491
  url: https://github.com/Shadow-Azure/harness-evolution/issues/491
```

## Background

Today case-level attribution confidence is a fixed 0.8 default at write time (`crud/bad_cases.py`). The merged design (#487) keeps model confidence out of the attribution step: whether evidence is complete is rule-decidable, the case-level score only feeds the step-4 display and an optional low-confidence gate, and model scoring moves to the cluster level after clustering (bugfix-19).

## Goals

- `bad_case_analysis.confidence` becomes an **evidence-completeness rule score**: three signals counted — order comparable (order=comparable), error signature match (overlap with the object's known failure signatures), and direct version proof (body hash / revision exact hit); vote count maps to a band (three votes ≥0.9; two votes 0.7–0.9; one vote around 0.5; contradictory signals <0.5).
- The score is deterministic and unit-testable: same evidence, same score, zero model calls, zero extra cost.
- The attribution engine stays `rule-v1`; the cache-key namespace is unchanged.

## Design basis

- [07 §5.5.2](../../../plans/fullstack-design/07-backend-implementation.md): the "attribution confidence stays rule-based" bullet and the three signal definitions.
- The Agent Note (adr): the recorded rejection of per-case model confidence.

## Implementation

- Extract the three signals on the attribution write path (the data already exists in `potential.py` anchor comparisons and version identity; surface it as needed).
- Vote-count and band-mapping functions plus unit tests (including contradictory-signal cases).
- The optional "low-confidence excluded from clustering" gate ships as a constant switch, off by default and not enabled in this issue.

## Steps

1. Signal extraction and the vote-mapping function with tests.
2. Replace the 0.8 default on the write path.
3. Regression over existing attribution tests (the step-4 change is only the score's provenance; fields and types unchanged).
4. Gates: `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`, `pnpm verify:flow`.

## Dependencies and delivery boundary

- Dependencies: none (fully independent of the provider chain; parallelizable).
- Delivery boundary: only the confidence output of the attribution write path and its tests; no schema, cache-key, or API-field changes.

## Independent verification

```sh
pnpm test:api -- tests/test_attribution_confidence.py
```

- The three-signal combination matrix (0–3 votes plus contradiction) hits every asserted band.

## Acceptance criteria

- The fixed 0.8 default is replaced by the vote mapping; matrix tests pin the band boundaries.
- Step-4 API confidence semantics are unchanged (0–1 float); zero frontend changes.
- Engine name and cache keys unchanged; historical caches unaffected.
- CI green.

## Gates and CI

- api-static / unit-tests-api / docs-flow.
- Commit and PR titles carry `(#N)`.

## Non-goals

- No per-case model confidence (the budget-switch slot is reserved, not implemented here).
- No cluster-level confidence changes (bugfix-19).
- No enabling of the low-confidence clustering gate.
