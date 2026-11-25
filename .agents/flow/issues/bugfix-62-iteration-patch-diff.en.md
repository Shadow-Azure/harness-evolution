# Step 6 edit patch colors whole-file overwrite content as a diff

English | [中文](bugfix-62-iteration-patch-diff.md)

```yaml flow
kind: issue
id: bugfix-62
milestone: bugfix
depends:
  - bugfix-21
  - bugfix-27
priority: P2
status: done
scope:
  - apps/api/app/service/evolution/**
  - apps/api/tests/**
  - apps/web/src/pages/evolution/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 617
  url: https://github.com/Shadow-Azure/harness-evolution/issues/617
```

## Background

### Scenario

At 19:36 CST on 2026-11-25, an admin opened step 6 of production run `01M8957ATHZX4K48K9PGXSVSVK` and expanded turn 4 (cluster `01M895G2RYCDA4M6XG5WC53QVX`, accepted at 85.0 vs 80.0). "Generated patch (current → candidate)" showed 478 lines, of which 147 were styled as red deletions, 0 as additions, and 331 as context. The red lines began with the YAML front-matter separator `---` and the Markdown bullet `- **所有模式**…`.

The real `unifiedDiff` in that turn's `candidate_committed` event (stored outside `round.patch`, in the run log) has 72 added lines and 0 deleted lines; the target file grew from 406 to 478 lines, and turns 1-4 never rolled the file back. The page did not show a diff at all: it showed the whole-file overwrite content that agent-edit turns persist.

### Analysis

- After `#488`, an agent-edit `round.patch` stores `files[] / note / intent / report` (plus legacy `file / lines / overwrite` for one file); `files[].lines` holds the **whole file** after applying the EditPlan.
- `#522` fixed the 500 when reading that shape, but `StepRoundPatch` still had no diff field, and `DiffView.vue` kept classifying `files[].lines` by the `+` / `-` / `@@` prefix. Markdown bullets and `---` matched `startsWith("-")` and rendered as deletions.
- `intent`, `report`, and the candidate's real `unifiedDiff` already existed; they simply never reached the step-6 read model. Tests used hand-built `-old / +new` lines and never fed the real whole-file output through.

## Goals

- Step 6 shows only the real change slice, never treating Markdown bullets or front-matter separators in a whole file as deletions.
- New rounds get the real diff directly from persisted data; historical rounds degrade safely without red deletion false positives.
- Frontend and backend agree on one `patch.diff` / `patch.files` contract, locked by regression tests.
- Keep the existing patch / candidate / push / eval / acceptance structure; do not change evaluation or git behavior.

## Design authority

- [05 §3.6](../../../plans/fullstack-design/05-api-design.md): the `rounds[]` contract and patch projection for `steps/iteration`.
- [08 §10.3](../../../plans/fullstack-design/08-frontend-implementation.md): the step-6 patch / candidate / push / eval / acceptance rendering structure.
- [07 §5.5.4](../../../plans/fullstack-design/07-backend-implementation.md): agent-edit read-only exploration, EditPlan application, and intent / diff audit.
- [`bugfix-27`](bugfix-iteration-patch-read.en.md) and [`bugfix-21`](bugfix-agent-edit-iteration.en.md): prior facts about this read model and the agent-edit stored shape.

## Implementation

- `apps/api/app/service/evolution/git_candidate.py`: after a candidate commit succeeds, write the real `unified_diff` back into `round.patch.diff`; `_stored_patch()` can also serialize `PatchBundle.unified_diff`.
- `apps/api/app/service/evolution/round_patch.py`: `stored_bundle()` reads `diff` back and stays compatible with old shapes.
- `apps/api/app/service/evolution/stages.py`: add `StepRoundPatch.diff: list[str] | null`; project the stored diff first, otherwise synthesize change blocks from `intent` + `report.status == "applied"`, and return `null` when neither exists.
- `apps/web/src/pages/evolution/components/DiffView.vue`: with a `diff`, render the real unified diff per file block and keep file-header lines out of the add/delete counts; with `diff: null`, show the neutral whole-file preview without `+` / `-` / `@@` classification.
- `packages/contracts`, `apps/api/tests`, `apps/web/src/**/*.test.ts`, `tests/e2e`, `plans/fullstack-design/05-api-design.md`, `plans/fullstack-design/08-frontend-implementation.md`: contract, regression tests, E2E fixture, and design docs in sync.

## Implementation steps

1. Persist the diff on the write side and pin the `_stored_patch()` → `stored_bundle()` write/read cycle with a unit test.
2. Project `diff` on the read side, with the intent/report fallback and the no-diff `null` branch.
3. Switch the frontend to diff-first with a neutral whole-file fallback, and add regressions for `---` and Markdown bullets.
4. Regenerate the OpenAPI contract, update the design docs and the E2E fixture, and run the focused gates.
5. After deployment, recheck turn 4 of `01M8957ATHZX4K48K9PGXSVSVK` and confirm the red deletions are gone.

## Dependencies and boundary

- Dependencies: `bugfix-21` (agent-edit intent / diff persistence) and `bugfix-27` (patch read model).
- Boundary: only step-6 patch persistence, reading, rendering, and tests; no diff recomputation, no changes to patch generation, clustering, evaluation, or push.
- No data migration for historical rounds: show change blocks from `intent` / `report`; rounds without usable data show the neutral whole-file preview and never a fabricated diff.

## Verification

```sh
pnpm test:api tests/evolution/test_iteration_round_patch.py
pnpm test:api tests/m5-11-evolution-recovery/test_full_placeholder_loop.py
pnpm test:web
pnpm typecheck:web
pnpm contract:check
pnpm test:e2e --pattern m10-06
pnpm verify:flow
```

- Expected: a new turn's `patch.diff` comes from the persisted `candidate.unifiedDiff`; a historical turn's `patch.diff` holds change blocks synthesized from applied edits; with no diff and no intent it is `null`; the page no longer shows red `---` or `- **所有模式**` in turn 4.

## Acceptance

- Turn 4 shows the real diff or change blocks that match its cluster, and the red deletion false positives are gone.
- A new turn's `patch.diff` comes from the persisted `candidate.unifiedDiff`; historical turns show change blocks from `intent` / `report`, or degrade to the uncolored whole-file preview.
- Tests cover `---` and `- ` lines from the real persisted output and assert they are not deletions, and also cover rounds with no intent / no diff.
- Contract, design docs, and E2E evidence are updated, and CI is green.

## Gates and CI

- `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`, `pnpm test`, `pnpm typecheck:web`, `pnpm contract:check`, `pnpm test:e2e --pattern m10-06`, `pnpm verify:flow`, `pnpm verify:docs`.
- Commits and the PR title carry `(#617)`.

## Non-goals

- No changes to cluster review/score generation or to the `cluster_probe.description` format.
- No changes to patch generation strategy, `EDIT_BUDGET`, `MAX_CONTENT_LINES`, or the agent tool surface.
- No changes to evaluation, push, the candidate state machine, or the final commit message.
- No batch migration of historical rounds and no rewrite of already-accepted stored content.
