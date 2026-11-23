# agent-edit patch source: structured edits, deterministic apply, and audit

English | [中文](bugfix-agent-edit-iteration.md)

```yaml flow
kind: issue
id: bugfix-21
milestone: bugfix
depends:
  - bugfix-17
  - bugfix-20
priority: P2
status: done
scope:
  - apps/api/app/main.py
  - apps/api/app/service/evolution/**
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/tests/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 488
  url: https://github.com/Shadow-Azure/harness-evolution/issues/488
```

## Background

With the EditPlan mechanics (bugfix-20) and the Claude Code subclass (bugfix-17) in place, patch generation moves onto the real loop: `agent-edit` becomes the third patch source and edit_workspace runs "read-only exploration → plan submission → deterministic apply → diff → commit → push → eval". An eval reject keeps the existing "end this turn, continue to the next cluster" state machine; there is no automatic turn-level retry.

## Goals

- Add `AgentEditPatchSource` (registering `agent-edit` in `PATCH_SOURCE_MODES` and the factory, keeping the "run-frozen config first, env fallback" selection semantics): the goal carries the cluster title/description plus representative case evidence and fix requirements; `allowed_paths` confines to the sub_dir.
- `edit_workspace` wiring: the agent tool surface is read-only plus `Write(./.harness-evolution/edits.json5)`; the EditPlan is collected and validated through the submission channel, applied by edits.py on a temporary mirror, and lands as a PatchBundle candidate.
- Safety gates: the applier never writes the real repository, so out-of-scope or failing edits only affect the scratch mirror; diff + intent + report land in run events. Cost protection uses the existing process-level means (a `--max-turns` constant plus timeout constants); **no run-level budget gate** (add one later under real cost pressure).
- Failure handling: a plan that cannot be applied, or a provider failure, fails or pauses this turn; no feedback is injected into a next turn.

## Design basis

- [07 §5.5.4](../../../plans/fullstack-design/07-backend-implementation.md): execution flow, safety gates, and patch-source integration.
- [07 §5.6](../../../plans/fullstack-design/07-backend-implementation.md): the existing single-turn candidate → push → evaluation state machine.

## Implementation

- AgentEditPatchSource and single-turn candidate wiring (submit a plan → apply on a temporary mirror → multi-file bundle → commit → push → eval).
- E2E: a full run (fake provider) producing a bundle end to end; a real-CLI smoke switch.

## Steps

1. AgentEditPatchSource + edit_workspace wiring (testable under fake).
2. Multi-file candidate, intent/report/diff audit, and tests.
3. Gates: `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`, `pnpm test:e2e --pattern evolution`, `pnpm verify:flow`.

## Dependencies and delivery boundary

- Dependencies: bugfix-17 (real subclass), bugfix-20 (applier and bundle).
- Delivery boundary: patch generation and single-turn candidate wiring; no automatic turn-level retry, no clustering changes (bugfix-19) and no eval-gateway internals.

## Independent verification

```sh
pnpm test:api -- tests/test_agent_edit_source.py
pnpm test:e2e --pattern evolution
```

- Under fake, a full run produces "structured plan → deterministic apply → multi-file diff → candidate"; an inapplicable plan fails without retrying.

## Acceptance criteria

- With `HE_PATCH_SOURCE_MODE=agent-edit` (or the run-frozen config) a full run yields a real multi-file diff committed as a candidate; intent-vs-diff consistency is auditable (intent + report persisted).
- An eval reject ends the turn through the existing rejection path and does not open a next turn.
- Switching env back to placeholder restores today's behavior.
- CI green.

## Gates and CI

- api-static / unit-tests-api / docs-flow / e2e.
- Commit and PR titles carry `(#N)`.

## Non-goals

- No automatic turn-level retry, `--resume` feedback, or rejected-edit buffer (decision on 2026-11-23: fail means reject).
- No direct-edit mode switch.
- No run-level budget gate or its config (add later under real cost pressure).
- No eval-gateway scoring changes.
- No vectorized grouping.
