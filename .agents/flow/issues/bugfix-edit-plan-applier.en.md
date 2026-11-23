# EditPlan contract, deterministic edits.py applier, and PatchBundle

English | [中文](bugfix-edit-plan-applier.md)

```yaml flow
kind: issue
id: bugfix-20
milestone: bugfix
depends:
  - bugfix-15
priority: P2
status: done
scope:
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/app/third_party_api/git/workspace.py
  - apps/api/app/service/evolution/patch_source.py
  - apps/api/tests/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 494
  url: https://github.com/Shadow-Azure/harness-evolution/issues/494
```

## Background

The merged design (#487) adopts SkillOpt-style edit instructions for patches: the agent submits an EditPlan, a deterministic applier executes it, and `git diff` is the single truth. This issue delivers the mechanical "plan → apply → diff → bundle" parts, decoupled from providers and business flow, independently testable.

## Goals

- **EditPlan contract** (`third_party_api/ai_agent/edits.py`): `{summary, edits: [{op: append|insert_after|replace|delete, file, target?, content?, rationale}]}`, with a Pydantic model as the single source of truth.
- **Deterministic applier**: applies pure-text operations in order (replace/delete first match, insert_after at the line boundary after the anchor, append at EOF), emitting a per-edit status report (`applied / skipped_anchor_missing / error`) with live re-checks of later anchors.
- **Semantic validation**: `file ∈ allowed_paths`; anchors for replace/delete/insert_after must **exist and be unique** in the file (ambiguity rejected); `len(edits) ≤ edit_budget` (default 8, enforced twice — prompt constraint plus hard truncation); a per-edit content line cap.
- **PatchBundle**: `{files, unified_diff, note=intent.summary, intent=EditPlan, report=per-edit statuses}`; the `PatchSource` protocol gains `build_bundle()` (default implementation wraps the old `build()` as a single-file bundle, zero changes to existing sources); the candidate commit flow submits per bundle with `Harness-Patch-Hash` idempotency preserved.

## Design basis

- [07 §5.5.4](../../../plans/fullstack-design/07-backend-implementation.md): the EditPlan data contract, execution flow, safety gates, and "intent state plus result state in one".
- [07 §5.6](../../../plans/fullstack-design/07-backend-implementation.md): the existing candidate-commit and push seams.

## Implementation

- edits.py: models, validators, the applier, status reports; the `.harness-evolution/` path stays out of the applied scope.
- patch_source.py: the `build_bundle()` default and a reserved `agent-edit` key in `PATCH_SOURCE_MODES` (the real source is bugfix-21).
- git/workspace.py: multi-file add and hashing for bundle-based candidate commits.

## Steps

1. EditPlan model + validators + applier unit tests.
2. PatchBundle and the `build_bundle()` default.
3. Workspace multi-file commit changes with regression.
4. Gates: `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`, `pnpm verify:flow`.

## Dependencies and delivery boundary

- Dependencies: bugfix-15 (package skeleton).
- Delivery boundary: mechanical components and bundle changes only; no agent invocation or iteration loop (bugfix-21).

## Independent verification

```sh
pnpm test:api -- tests/test_edit_plan_applier.py
```

- The four ops, anchor missing/ambiguous, sequential cross-effects, budget truncation, and scope exclusion all have assertions.

## Acceptance criteria

- The same EditPlan on the same base yields a byte-identical diff (deterministic replay).
- Ambiguous anchors and out-of-scope files are rejected with locateable errors; `.harness-evolution/` never enters the diff.
- The old placeholder/minimal-config sources behave identically (proven by regression).
- CI green.

## Gates and CI

- api-static / unit-tests-api / docs-flow.
- Commit and PR titles carry `(#N)`.

## Non-goals

- No agent-edit source or iteration loop (bugfix-21).
- No rejected-edit buffer.
- No eval-gateway changes.
