# Iteration edit patch shows mass deletions: whole-file overwrite content is rendered as a diff

English | [中文](bugfix-iteration-patch-fullfile-diff-render.md)

```yaml flow
kind: issue
id: bugfix-62
milestone: bugfix
depends:
  - bugfix-21
  - bugfix-27
priority: P2
status: ready
scope:
  - apps/api/app/service/evolution/**
  - apps/web/src/pages/evolution/**
  - packages/contracts/**
  - apps/api/tests/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 617
  url: https://github.com/Shadow-Azure/harness-evolution/issues/617
```

## Background

Step 6, iteration, is the only place where the self-evolution flow can verify what changed, why it changed, how much the score moved, and which commit was accepted. `#522` (bugfix-27) fixed the 500 on this step: the `round.patch` storage grew from the single-file `file / lines / note` shape to `files[] / note / intent / report`, and the reader restores the bundle before projecting `StepRoundPatch`.

Once the read path worked, the render path still assumed `files[].lines` were unified-diff lines prefixed with `+`, `-`, or `@@`. `DiffView.vue` colors each line by its first character, while an agent-edit turn stores the whole post-overwrite file. On 2026-11-25 19:36 (CST), an admin opened step 6 of production run `01M8957ATHZX4K48K9PGXSVSVK`; the turn-4 patch area therefore showed a large red "deletion" block. The real change at the same position consisted of 72 additions and 0 deletions.

## Problem statement

### Observed behavior

The production page is `http://8.149.232.63/workspaces/01M7KJ05ENF9784GPBDV544VB0/evolution/runs/01M8957ATHZX4K48K9PGXSVSVK?step=iteration`. Turn 4 uses cluster `01M895G2RYCDA4M6XG5WC53QVX` ("prompt issue: acceptance items are not turned into executable checks and coverage is not reconciled") and was accepted (85.0 vs. 80.0, +5.0).

The expanded "generated patch (current → candidate)" block shows 478 lines: 147 lines receive the red deletion style, 0 lines are marked as additions, and 331 lines are shown as context. The red lines begin with `---` (the YAML front-matter delimiter) and `- **All modes**...` (Markdown unordered-list items); they are not removed content.

### Data-side comparison

The real `unifiedDiff` in the turn-4 `candidate_committed` event contains 72 additions and 0 deletions. The target file grew from 406 lines in turn 3 to 478 lines in turn 4. Turns 1 through 4 are all addition-only; no turn rewound or removed the file wholesale. The turn-4 `round.patch` also stores `intent` (three edits) and `report` (per-edit apply status); the `replace` / `insert_after` targets all belong to the acceptance-coverage gate, which directly matches the selected cluster.

### Verification of the reported "error"

Following the page path, the run had no terminal error: turn 4 was evaluating, turn 5 then entered evaluation, four turns were accepted, `error` was `null`, and the execution log had no `run_failed`. The same target's earlier run `01M885592456VVK5B68DSMRKTE` did fail in the turn-3 patch stage with `claude-code edit submission failed validation`; its root cause (the validator rejected a multi-line `insert_after` anchor) was analyzed in `#599` and fixed by `#607`, which is a different path from this run's whole-file preview. This issue covers only the display-contract defect that renders whole-file content as mass deletion.

### Impact

The display makes it look as if the self-evolution candidate deleted most of the skill, which can lead reviewers to misjudge model quality or request a rollback of a change that only adds content. Because the block shows the complete `SKILL.md` instead of the changed fragments, reviewers also cannot see how the change relates to `cluster_probe.description` from step 6; the real change is only visible by reading `unifiedDiff` in the `candidate_committed` execution-log event.

## Goals

- Show only the real change fragments in the step-6 patch area; never treat Markdown lists or front-matter delimiters in the whole file as deletion lines.
- Let new turns obtain the real diff from stored data; historical turns must degrade safely when no diff exists and must not produce red "deletion" false positives.
- Give `patch.lines` / `patch.diff` one frontend-backend contract and lock it with regression tests.
- Keep the existing patch / candidate / push / eval / acceptance structure of step 6, and do not change evaluation or git behavior.

## Input basis (cluster_probe.description vs. the edit patch)

**Conclusion: the patch is not generated directly from `cluster_probe.description`.** `cluster_probe.description` (stored as `probe_clusters.probe_cluster_description`) is one prompt input; the actual patch is an `EditPlan` produced by the model after read-only exploration of the workspace, after which the deterministic applier overwrites the whole target file with the new content. The page shows the post-overwrite whole file, so "what changed relative to the previous revision" is lost.

- `cluster_llm._compose_description()` composes the cluster description as `{type} issue · {title} · {summary}` (bounded), and `stages._cluster_title()` only takes the first two segments for the card title without changing the full prompt description.
- `advance.build_candidate_trace()` puts `cluster.probe_cluster_description` into `CandidateTrace.cluster_title`, the deduplicated `probe_analysis` into `analysis`, and each `probe_description` into `sources[].description`.
- `patch_source._edit_prompt()` uses `cluster_title` (≤300 chars), `analysis` (≤1800 chars), and at most five representative evidence lines (each description ≤240 chars or analysis ≤360 chars), then appends allowed paths, the edit budget, and the instruction to prefer a minimal, revertible real fix.
- `apply_edit_plan()` applies the plan to a scratch mirror; `_patch_from_content()` splits the applied file into `lines` and marks `overwrite=True`; `_stored_patch()` stores `files[].lines / overwrite`, `note`, `intent`, and `report`.
- `git_candidate.publish()` writes the real `candidate.unified_diff` only into the `candidate_committed` event; `stages._round_patch()` projects only `file / lines / overwrite`, `StepRoundPatch` has no diff field, and `DiffView.vue` then colors the whole file by leading `+` / `-` / `@@`.

## Root-cause analysis

### Conclusion

The direct cause is that the read contract and the render contract interpret `lines` in opposite ways: an agent-edit turn stores the whole post-overwrite file, while the frontend treats it as a unified diff and classifies line by line. Every Markdown unordered-list item (`- `) and YAML front-matter delimiter (`---`) matches `startsWith("-")` and is rendered as a deletion; the real diff's addition prefix is absent, so only "mass deletion" remains visible.

The systemic cause is that step 6's auditable information is truncated: `intent`, `report`, and the real `unifiedDiff` all exist, but none enters the `StepRoundPatch` read model, so the page can only use the whole file as a stand-in for the diff. The tests also used only synthetic `-old / +new` lines and never fed the real full-file output of `_stored_patch()` through the Markdown case, so CI did not catch it.

### Analysis process

1. Logged into the production frontend as admin, opened step 6 of the run above, and expanded turn 4; DOM counts were 478 `.dline`, 147 `.dline.del`, 0 `.dline.add`, and 331 `.dline.ctx`, with the first `.del` texts being `---` and `- **All modes**...`.
2. Read `GET /api/evolution/runs/{id}/events` for the same run; the `unifiedDiff` of the turn-4 `candidate_committed` event had 72 additions and 0 deletions, contradicting the 147 deletions on the page and proving the page did not render that diff.
3. Read `GET /api/evolution/runs/{id}/steps/iteration`; turn 4's `patch.files[0]` had 478 lines and `overwrite=true`, with no `diff` field; that is whole-file content, not a diff.
4. Traced the backend chain: `_patch_from_content()` produces the whole file, `_stored_patch()` stores only the whole file plus intent/report, `_round_patch()` projects only `file / lines / overwrite`, and `DiffView.vue`'s `lineClass()` only inspects the first character.
5. Cross-checked the real edit plan: turn 4's three `intent.edits` replace or insert the "establish an acceptance matrix" and "acceptance-coverage gate" sections, showing the change is indeed related to the cluster description; the page looks unrelated only because it shows all 478 lines instead of those three changes.
6. Checked the tests: the DiffView case in `RunDetailConformance.test.ts` passes only synthetic `@@ / -old / +new / context` lines; the API tests only assert patch shape and file count, and never feed the real `_stored_patch()` output (with Markdown lists and `---`) into the read model and renderer.

### Responsibility boundary

- The model did not delete content, and the cluster description or attribution inputs are not wrong: the real turn-4 diff has 0 deletions, and all three edits center on the selected cluster's acceptance gate.
- This is not a regression of `#522` (the read 500): the run's `steps/iteration` already returns 200, and the problem occurs after projection.
- This is not `#599` (the multi-line `insert_after` validation failure): that defect occurs only in the patch-generation stage and fails the run; all edit calls in this run succeeded.
- This is not an evaluation, push, or git-candidate problem: turns 1 through 4 were pushed and accepted, and the run state is normal.

## Recommended solution (single)

**Change the step-6 patch contract to carry and render the real diff: persist the candidate's real `unifiedDiff` on the write side, project `patch.diff` on the read side, and render only the diff; for historical turns, synthesize change blocks from the stored `intent` + `report` and never color whole-file lines by `-`.**

1. Write side: after the candidate commit, `git_candidate.publish()` writes `candidate.unified_diff` into `round.patch` (reusing `PatchBundle.unified_diff`), and `round_patch.stored_bundle()` reads it back; do not recompute the diff.
2. Read side: add `diff: list[str] | None` to `StepRoundPatch`; `_round_patch()` prefers the stored diff, falls back to synthesizing `-` / `+` / hunk lines from applied edits in `intent` (using `report` status), and returns `null` when neither exists.
3. Frontend: when `patch.diff` exists, `DiffView` renders only the diff; when it is `null`, render a neutral "candidate file content (whole-file preview)" without `+` / `-` / `@@` classification and without marking Markdown lists or `---` red.
4. Contracts and tests: run `pnpm contract:generate` to update `packages/contracts`; in `apps/api/tests`, use the real `_stored_patch()` output (478 whole-file lines including 147 `-`-prefixed lines) to assert the read model no longer treats it as a diff; cover `---` and `- ` lines in Web unit tests; add an E2E screenshot comparison using this run or an equivalent fixture.
5. After deployment, verify with this run: turn 4 shows only 72 additions and 0 deletions, the red deletion count is zero, and historical turns also show change blocks that match the cluster.

## Design authority

- [05 §3.6](../../../plans/fullstack-design/05-api-design.md): the `steps/iteration` `rounds[]` contract and patch projection rules.
- [08 §10.3](../../../plans/fullstack-design/08-frontend-implementation.md): the step-6 patch / candidate / push / eval / acceptance rendering structure.
- [07 §5.5.4](../../../plans/fullstack-design/07-backend-implementation.md): agent-edit read-only exploration, EditPlan application, and intent / diff auditing.
- `.agents/flow/issues/bugfix-iteration-patch-read.md` (`#522`) and `bugfix-agent-edit-iteration.md` (`#488`): prior facts for the read model and the agent-edit storage shape.

## Implementation

- `apps/api/app/service/evolution/git_candidate.py`: write `unifiedDiff` into the turn patch after the candidate commit.
- `apps/api/app/service/evolution/round_patch.py`: parse the stored diff and stay compatible with the old shape.
- `apps/api/app/service/evolution/stages.py`: add the `diff` projection to `StepRoundPatch` and implement the intent/report fallback for historical turns.
- `apps/web/src/pages/evolution/components/DiffView.vue`: render the diff, and use a neutral preview when falling back to the whole file.
- `packages/contracts`, `apps/api/tests`, `apps/web/src/**/*.test.ts`, `tests/e2e`, `plans/fullstack-design/05-api-design.md`, and `plans/fullstack-design/08-frontend-implementation.md`.

## Implementation steps

1. Persist the diff on the write side and pin the `_stored_patch()` → `stored_bundle()` save/load cycle with a unit test.
2. Project `diff` on the read side and add the intent/report fallback and the no-diff `null` branch.
3. Switch the frontend to diff-first rendering and neutral whole-file fallback, and add regression cases for `---` and Markdown lists.
4. Update the OpenAPI contract, design docs, and E2E fixture, then run the focused gates.
5. After deployment, verify on turn 4 of `01M8957ATHZX4K48K9PGXSVSVK` that the red deletion count is zero.

## Dependencies and boundary

- Dependencies: `bugfix-21` (agent-edit intent / diff storage) and `bugfix-27` (the patch read model).
- Boundary: change only step-6 patch persistence, reading, rendering, and tests; do not recompute the git diff or change patch generation, clustering, evaluation, or push.
- No data migration for historical turns: use the `intent` / `report` fallback; when no usable data exists, show the neutral whole-file preview instead of fabricating a diff.

## Independent verification

```sh
TOKEN=$(curl -s -X POST http://8.149.232.63/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"<AI_EVAL_PASSWORD>"}' | jq -r .accessToken)
curl -s -H "Authorization: Bearer $TOKEN" "http://8.149.232.63/api/evolution/runs/01M8957ATHZX4K48K9PGXSVSVK/steps/iteration" | jq '.payload.rounds[] | select(.roundId == "01M895GAE675SWVN0B2789W5J5") | .patch'
```

- Expect `diff` to exist with 72 `+` lines and 0 real deletion lines; turn 4 must no longer show red `---` or `- **All modes**` lines.
- Run `pnpm test:api`, `pnpm test`, `pnpm typecheck:web`, `pnpm contract:check`, `pnpm test:e2e --pattern evolution`, and `pnpm verify:flow`; all must pass.

## Acceptance

- Turn 4 shows the real diff: 72 additions, 0 deletions, and the 147 red false positives are gone.
- New turns take `patch.diff` from the stored `candidate.unifiedDiff`; historical turns such as this run show change blocks synthesized from `intent` / `report`, or degrade to a neutral whole-file preview.
- Tests cover `---` and `- ` lines from the real `_stored_patch()` output and ensure they are not judged as deletions; they also cover turns without intent or diff.
- The contract, design docs, and E2E evidence are updated together, and CI is green.

## Gates and CI

- `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`, `pnpm test`, `pnpm typecheck:web`, `pnpm contract:check`, `pnpm test:e2e --pattern evolution`, `pnpm verify:flow`, and `pnpm verify:docs`.
- Commit and PR titles carry `(#N)`.

## Non-goals

- Do not change `cluster.review` / `cluster.score` clustering or description generation, and do not change the format of `cluster_probe.description`.
- Do not change the patch-generation strategy, `EDIT_BUDGET`, `MAX_CONTENT_LINES`, or the agent tool surface.
- Do not change evaluation, push, the candidate state machine, or the final commit message.
- Do not do batch data migration for historical turns or rewrite the stored content of accepted turns.
