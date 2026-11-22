# agent-edit patch source and iteration loop: resume feedback, rejected-edit buffer, and budget gate

English | [中文](bugfix-agent-edit-iteration.md)

```yaml flow
kind: issue
id: bugfix-21
milestone: bugfix
depends:
  - bugfix-17
  - bugfix-20
priority: P2
status: backlog
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/tests/**
  - tests/e2e/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 488
  url: https://github.com/Shadow-Azure/harness-evolution/issues/488
```

## Background

With the EditPlan mechanics (bugfix-20) and the Claude Code subclass (bugfix-17) in place, patch generation moves onto the real loop: `agent-edit` becomes the third patch source and edit_workspace runs "read-only exploration → plan submission → deterministic apply → diff → commit → push → eval", iterating with feedback after rejects.

## Goals

- Add `AgentEditPatchSource` (registering `agent-edit` in `PATCH_SOURCE_MODES` and the factory, keeping the "run-frozen config first, env fallback" selection semantics): the goal carries the cluster title/description plus representative case evidence and fix requirements; `allowed_paths` confines to the sub_dir.
- `edit_workspace` wiring: the agent tool surface is read-only plus `Write(./.harness-evolution/edits.json5)`; the EditPlan is collected and validated through the submission channel, applied by edits.py, and lands as a PatchBundle candidate.
- **Iteration loop**: after an eval reject, `--resume` continues the same session with feedback (delta, failure reasons) plus a **rejected-edit buffer** (the previous EditPlan summary: rejected edits must not repeat or reappear in disguise); the session id persists on the turn record.
- Safety gates: out-of-scope edits roll back via `git checkout -- .`; diff + intent + report land fully in run events. Cost protection uses the existing process-level means (a `--max-turns` constant plus timeout constants); **no run-level budget gate** (add one later under real cost pressure).

## Design basis

- [07 §5.5.4](../../../plans/fullstack-design/07-backend-implementation.md): execution flow, iteration loop, safety gates, and patch-source integration.
- [07 §5.6](../../../plans/fullstack-design/07-backend-implementation.md): the existing single-turn candidate → push → evaluation state machine.

## Implementation

- Patch source and turn-loop wiring (reject → resume with feedback and the rejection buffer → next turn).
- E2E: a full run (fake provider) producing a bundle end to end; a real-CLI smoke switch.

## Steps

1. AgentEditPatchSource + edit_workspace wiring (testable under fake).
2. Iteration loop and rejected-edit buffer with tests.
3. Gates: `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`, `pnpm test:e2e --pattern evolution`, `pnpm verify:flow`.

## Dependencies and delivery boundary

- Dependencies: bugfix-17 (real subclass), bugfix-20 (applier and bundle).
- Delivery boundary: patch generation and the iteration loop; no clustering changes (bugfix-19) and no eval-gateway internals.

## Independent verification

```sh
pnpm test:api -- tests/test_agent_edit_source.py
pnpm test:e2e --pattern evolution
```

- Under fake, a full run produces "structured plan → deterministic apply → multi-file diff → candidate"; the reject path's resume feedback and rejection buffer have assertions.

## Acceptance criteria

- With `HE_PATCH_SOURCE_MODE=agent-edit` (or the run-frozen config) a full run yields a real multi-file diff committed as a candidate; intent-vs-diff consistency is auditable (intent + report persisted).
- After a reject the next turn carries feedback and the rejection buffer; turn caps take effect.
- Switching env back to placeholder restores today's behavior.
- CI green.

## Gates and CI

- api-static / unit-tests-api / docs-flow / e2e.
- Commit and PR titles carry `(#N)`.

## Non-goals

- No direct-edit mode switch.
- No run-level budget gate or its config (add later under real cost pressure).
- No eval-gateway scoring changes.
- No vectorized grouping.
