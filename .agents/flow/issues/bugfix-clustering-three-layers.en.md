# Three-layer clustering integration: review and scoring tasks, hybrid-lexical-llm-v1, and fallbacks

English | [中文](bugfix-clustering-three-layers.md)

```yaml flow
kind: issue
id: bugfix-19
milestone: bugfix
depends:
  - bugfix-15
  - bugfix-16
priority: P2
status: in-progress
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/app/db/crud/attributions.py
  - apps/api/app/main.py
  - apps/api/tests/**
  - tests/**
  - packages/contracts/**
  - scripts/**
  - .github/workflows/ci.yml
  - plans/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 493
  url: https://github.com/Shadow-Azure/harness-evolution/issues/493
```

## Background

The merged design (#487) splits clustering into grouping (O(N), no LLM), review (O(K×s), merge and naming), and scoring (O(K×s), cluster confidence plus severity), with LLM input/output decoupled from the attribution-report volume N. This issue wires the review and scoring layers into the prepare pipeline; the grouping layer's vectorization upgrade is a later optional issue.

## Goals

- **Review layer**: one `analyze(task="cluster.review")` call — input is draft summaries (about 60 tokens per draft) plus 3–5 sampled representatives per draft; output uses draft-key references (`{"from": ["D1","D2"], "title": …}`) allowing merge/naming/summary only; hard gates are draft-partition integrity (every draft appears exactly once) and merge-only, with wholesale fallback on violation.
- **Scoring layer**: `cluster.score` (direct cluster confidence 0–1 with rubric anchoring and `evidence_refs ⊆ input` checking) and `severity.score` (dimensions 0–10 with a CoT grader; overall is the decision score, formula score kept as a metrics contrast, CVSS-style vector string) as two failure-isolated calls.
- The algorithm identifier upgrades to `hybrid-lexical-llm-v1` persisted with the run snapshot; cluster title/description/confidence/severity use the LLM output.
- Fallback matrix: review failure → drafts as-is; `cluster.score` failure → category constants; `severity.score` failure → the `cluster_severity()` formula; each records a `degraded` event.

## Design basis

- [07 §5.5.2](../../../plans/fullstack-design/07-backend-implementation.md): the three layers, the N-decoupling rule (draft-key references, representative sampling, statistic injection), the two scoring tasks, and the fallback matrix.
- [06 §5.3](../../../plans/fullstack-design/06-database-design.md): the confidence/severity/rank storage contract is unchanged — zero migrations.

## Implementation

- New task models and semantic validators in the service layer (partition integrity, reference subset, key-set equality); prompt templates and sampling-cap constants.
- The prepare pipeline inserts the two calls after the lexical draft pass (fully testable under the fake provider).
- Run events record `ai_agent_call` (task/model/tokens/cost/latency/outcome) and `degraded`.

## Steps

1. Task models + validators + unit tests (fake).
2. Prepare wiring and fallback-path tests.
3. Regression over existing clustering/seven-step tests (the lexical path's behavior unchanged).
4. Gates: `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`, `pnpm verify:flow`.

## Dependencies and delivery boundary

- Dependencies: bugfix-15 (provider skeleton), bugfix-16 (submission collection); the real claude-code backend (bugfix-17) is not required — acceptance is achieved with the fake.
- Delivery boundary: only clustering-related service orchestration and task models; no DB or API contract changes; no embedding grouping.

## Independent verification

```sh
pnpm test:api -- tests/test_clustering_three_layers.py
```

- Partition integrity (missing draft / duplicate reference rejected), reference-subset validation, and all three fallback paths have assertions.

## Acceptance criteria

- A cluster-only run (fake) works end to end: drafts → review merge → scoring persisted, with the algorithm identifier `hybrid-lexical-llm-v1`.
- Each fallback path triggers independently without blocking the run; the worst case equals today's behavior.
- LLM input scale follows cluster count and sampling, not N (sampling-cap constants with tests).
- CI green.

## Gates and CI

- api-static / unit-tests-api / docs-flow.
- Commit and PR titles carry `(#N)`.

## Non-goals

- No vectorized grouping or `SupportsEmbedding` (a later optional issue).
- No patch-generation changes (bugfix-20/21).
- No per-case model confidence.
