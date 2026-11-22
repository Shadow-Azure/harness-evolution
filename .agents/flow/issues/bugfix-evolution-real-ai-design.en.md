# Self-evolution real-model design: AI Agent Provider, three-layer clustering, instruction-style Edit patch

English | [中文](bugfix-evolution-real-ai-design.md)

```yaml flow
kind: issue
id: bugfix-14
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - plans/fullstack-design/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 486
  url: https://github.com/Shadow-Azure/harness-evolution/issues/486
```

## Background

The four model-driven stages of the seven-step self-evolution loop are placeholder implementations: clustering is the `lexical-jaccard-v1` lexical Jaccard pass (`cluster.py`), case-level confidence is a fixed 0.8 (`crud/bad_cases.py`) with cluster-level category constants, severity is a constant-product formula, and patches come from the deterministic placeholder / minimal-config sources; `docs/architecture.md` also lists "real evaluation and patch" as not yet available. On 2026-11-22 the real-model design was finalized (after surveying Sentry / BERTopic / SkillOpt / Aider and several review rounds: a unified AI Agent Provider seam, three-layer clustering, a self-built structured submission channel, and a SkillOpt-aligned instruction-style Edit patch). The finalized design must land in `plans/fullstack-design` as the single design basis for follow-up implementation issues. This issue delivers design documents and the decision record only — no code.

## Goals

- Add §5.5.1–§5.5.4 to `plans/fullstack-design/07-backend-implementation.md`: the AI Agent Provider outbound seam, three-layer clustering (grouping / review / scoring), the structured submission channel with the JSON reliability defense, and the instruction-style Edit patch.
- Add the `third_party_api/ai_agent/` line to the directory tree and the "model outbound" row to the §5.1 seam table in `plans/fullstack-design/04-backend-architecture.md`.
- Add one Agent Note recording the key trade-offs (three layers, self-built channel vs `--json-schema`, instruction-style vs direct agent editing).
- The design stays reversible: follow-up implementation lands in staged issues, and switching env back to fake / placeholder restores today's behavior.

## Design basis

- [07 §5.5.1–§5.5.4](../../../plans/fullstack-design/07-backend-implementation.md): the four sections added by this PR are the design itself (provider contract and factory, the N-decoupling rule and draft-partition integrity, the submission channel with six defense layers, the EditPlan contract and iteration loop).
- [04 §3 layering and §5.1 seams](../../../plans/fullstack-design/04-backend-architecture.md): where the ai_agent outbound seam lives and its boundary against the "no unified Provider layer" statement.
- [06 §5.3 cluster persistence](../../../plans/fullstack-design/06-database-design.md): the storage contract for confidence / severity / rank is unchanged — the three layers only change how values are produced, with zero migrations.

## Implementation

- Insert the four sections between §5.5 and §5.6 in 07; the §5.5 lexical clustering text is untouched and referenced as the first grouping-layer implementation.
- Add the `ai_agent/` line under `third_party_api/` in the 04 directory tree; add a "model outbound (self-evolution)" row to the §5.1 table plus one sentence clarifying that `ai_agent` is not a revival of the early unified Provider.
- Agent Note: `.agents/notes/proposed/feature/2026-11-22-evolution-real-ai-design.md` (triplet), recording the four decisions and the rejected alternatives.

## Steps

1. Branch `agent/docs-evolution-real-ai-design` from main.
2. Edit the two design documents 04 / 07.
3. Add the Agent Note triplet and run `pnpm record:i18n`.
4. Local gates: `pnpm verify:flow`, `pnpm lint:docs`, `pnpm test:gates`.
5. `pnpm flow:sync` to backfill the issue number.
6. Commit (without the HTML working drafts) and open the PR with `(#N)` in the title.

## Dependencies and delivery boundary

- Dependencies: gh authenticated (flow:sync backfills numbers); no code, database, or external-service changes.
- Delivery boundary: only the two `plans/fullstack-design` documents and `.agents/` (issue triplet + Note triplet) change; the `plans/2026-11-22-*` working drafts (md / HTML) stay out of the PR.

## Independent verification

```sh
pnpm verify:flow
pnpm lint:docs
pnpm test:gates
grep -c "5.5.1 AI Agent Provider" plans/fullstack-design/07-backend-implementation.md
```

- All four commands pass; grep prints 1 (the new section exists exactly once).

## Acceptance criteria

- 07 contains §5.5.1–§5.5.4 and 04 contains the `ai_agent` tree line and seam-table row; relative links inside the documents resolve.
- The Agent Note triplet is complete with matching i18n hashes; the PR diff contains only the listed files and no HTML.
- CI is green.

## Gates and CI

- docs-flow lane: doc-sync (`verify:docs`) and `test:gates`.
- `verify:flow --diff` checks the PR title `(#N)` and scope coverage (`plans/fullstack-design/**`, `.agents/**`).
- Commit and PR titles carry `(#N)`.

## Non-goals

- No code implementation (zero changes under `apps/`, `scripts/`, `packages/`).
- No API contract, database migration, or frontend changes.
- The `plans/2026-11-22-*` working drafts (md / HTML) are not committed.
- No vectorized grouping and no model / opencode subclass implementation (design upgrade slots only).
