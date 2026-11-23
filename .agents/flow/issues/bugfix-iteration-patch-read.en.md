# Iteration step 500s on stored patch payloads: the read contract lags the stored structure

English | [中文](bugfix-iteration-patch-read.md)

```yaml flow
kind: issue
id: bugfix-27
milestone: bugfix
depends:
  - bugfix-21
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
  number: 522
  url: https://github.com/Shadow-Azure/harness-evolution/issues/522
```

## Background

### Problem scenario

On 2026-11-23 10:54, the user (admin) opened run details in production `http://8.149.232.63/`:

- Run: `01M834EBAY3C9BB3TM8V85VHQN` (target `codespec-subagent-driven-development@openspec-cn-main-copy-ar-a7ec200-claude-core`, workspace `OpenSpec-cn_SWE-bench`)
- Path: `/workspaces/01M7KJ05ENF9784GPBDV544VB0/evolution/runs/01M834EBAY3C9BB3TM8V85VHQN?step=iteration`
- Symptom: step 6 "迭代优化" shows a red error card titled `EVOLUTION_RUN_STEP_UNAVAILABLE`, subtitle "加载失败", body "当前步骤读取失败，请重试", and a "重试" button at the bottom.

Production scene (step 6 replaced by the error card where the turn cards belong):

![Production run details step 6: iteration returns the error card](https://github.com/Shadow-Azure/harness-evolution/releases/download/iteration-step-500-evidence-20261123/prod-iteration-error.png)

The other six steps rendered normally in the same visit: run status "✓ 已完成 · 自进化有效", 7 associated sessions, 7 potential bad cases, 7 attributions, 1 cluster, final score 85.0 vs 80.0; the 21 execution log entries were complete. Clicking "重试" returned the same card.

### Reproduction and observation

1. Log in to admin in a browser and open the path above; the step 6 error card appears consistently. Network shows `GET /api/workspaces/<wid>/evolution/runs/<rid>/steps/iteration` returning 500, three retries all 500:

   ```json
   {"error":{"code":"INTERNAL","message":"internal server error","details":{"requestId":"req_a07a250ab8b34b94acd080ff76d4402c"}}}
   ```

2. The other six step endpoints of the same run all return 200: `range` / `sessions` / `potential` / `attribution` / `clusters` / `final`.
3. Another completed run (`01M80MSB72NFZNDKK2Q3YN991K`, created 2026-11-22 11:28) still returns and renders its turn cards at step 6.
4. The run's stored facts are complete: the `final` step returns 1 accepted change (commit `dfea5b04fba65fd270268fa1d8645b3a2b1f46a7`, cluster `01M834EBN8W2AWGT4K1JPG0VM8`), and the execution log shows the candidate was submitted, pushed, evaluated and accepted.

This rules out run state, evaluation, push, frontend routing and the step state machine: one run's persisted data throws while being read.

### V2 prototype comparison

The V2 prototype step 6 lives in `evStepIter()` / `evCluster()` in `plans/ui-prototype-v2/harness-evolution.html`: each cluster is one turn card; expanded, it shows the "来源 bad case" table, "归因复核", the generated edit patch (current → candidate) diff, the "评测对比（验证集）" block and the accepted commit card.

Prototype step 6 overview (stubbed data `EV-20261109-01`, deep-research, viewport 1500×1000; not the same run as production, only the same step's information structure and rendering):

![V2 prototype step 6: turn cards render normally](https://github.com/Shadow-Azure/harness-evolution/releases/download/iteration-step-500-evidence-20261123/proto-iteration.png)

Prototype turn details (patch diff / evaluation comparison / commit card) are in the acceptance screenshots: the fixed local smoke compares the same prototype position item by item.

Conclusion: the prototype renders turn content at this position, while production renders no turn card at all and replaces the whole block with an error card. This is not a style or density deviation; the read path for this step fails as a whole.

### Impact

- Step 6 is the only step where self-evolution can check "what changed, how much the evaluation improved, and what the final commit is". The latest run is invisible; users can only see the step 7 summary score.
- The frontend maps every backend 500 to `EVOLUTION_RUN_STEP_UNAVAILABLE`, leaving only a requestId and no actionable clue; retrying a deterministic failure is useless, so the page cannot self-diagnose.
- As long as turns keep the current stored shape, every later run reproduces this; it is not one bad row and not one particular bad case.

## Goals

- Step 6 returns 200 for both the current stored shape (multi-file bundle `files[] / note / intent / report`, plus legacy `file / lines / overwrite` for one file) and the historical shape (`file / lines / note`), and shows the turn content completely.
- Pin the writer → reader contract with regression tests so a future stored-shape upgrade cannot silently drift the read chain again.

## Design authority

- `plans/fullstack-design/05-api-design.md` §3.6 (`steps/iteration` `rounds[]`; the current example still uses a single-file `patch`)
- `plans/fullstack-design/08-frontend-implementation.md` §10.3 (step 6 keeps turn cards: patch / candidate / push / eval / accept)
- V2 prototype `plans/ui-prototype-v2/harness-evolution.html` `evStepIter()` / `evCluster()` / `evCommitBlock()`
- Agent Note `.agents/notes/proposed/feature/2026-11-22-evolution-real-ai-design.md` (real patch sources and audit record)

## Root cause

### Conclusion

Step 6 hands the database `round.patch` directly to `StepRoundPatch` validation, while `StepRoundPatch` still describes the old single-file shape and inherits `extra="forbid"` from `IdentityModel`. The stored `round.patch` shape has grown twice:

- `#436` (bugfix-02) added `overwrite` while writing to support pause/resume;
- `#488` (bugfix-21) added `files[] / intent / report` while writing to support agent edits.

The newest run's patch dictionary therefore contains `files / note / intent / report / file / lines / overwrite`. `model_validate` raises 4 `extra_forbidden` errors, `_iteration()` does not catch them, the exception bubbles up as a 500 `INTERNAL`, and the frontend maps every non-`STEP_NOT_READY` error to `EVOLUTION_RUN_STEP_UNAVAILABLE`.

### Analysis

1. **The frontend is only a display**: `apps/web/src/pages/evolution/RunDetail.vue#L929-L934` always renders `EVOLUTION_RUN_STEP_UNAVAILABLE` when `stepError && stepErrorCode !== 'STEP_NOT_READY'`; the code comes from the step query. The other six step queries succeed, ruling out routing and the step state machine.
2. **The backend step 6 read chain**: `_iteration()` in `apps/api/app/service/evolution/stages.py#L691` calls `list_rounds()` first, then `_round_item()` (`#L1031`) for each turn; `#L1058` uses `StepRoundPatch.model_validate(patch)` to validate the stored dictionary directly into the read model.
3. **The read model lags the write model**: `StepRoundPatch` (`stages.py#L244-L257`) only has `file / lines / note`; it inherits `IdentityModel`, and `apps/api/app/service/identity/schemas.py#L9-L13` sets `extra="forbid"`. Any extra key is a validation error.
4. **The current write model**: `_stored_patch()` in `apps/api/app/service/evolution/git_candidate.py#L1099-L1115` writes `files[]` (each file has `file / lines / overwrite`), `note`, `intent` and `report`; for one file it also merges the legacy `file / lines / overwrite`. This run's `candidate_committed` event shows a bundle with exactly one file, `skills/codespec-subagent-driven-development/.harness-evolution/candidate-r1.md`, so the stored shape is "legacy single file + 4 new keys".
5. **Local reproduction**: feeding the real output of `_stored_patch()` to the read model gives:

   ```python
   StepRoundPatch.model_validate(_stored_patch(bundle))
   # 4 validation errors for StepRoundPatch
   # files / intent / report / overwrite -> Extra inputs are not permitted
   ```

   A multi-file bundle is worse: besides the 3 extra keys it lacks the required `file` and `lines`, 5 errors in total. That is, even without this run's legacy keys, a multi-file patch produced by agent edits also 500s.

6. **Why only the latest run broke**: the `#436` deployment took effect after 2026-11-22 22:44, and `#488` was deployed at 2026-11-23 10:22; this run was created at 2026-11-23 10:40:58, the first run after both deployments. `01M80MSB…`, created 2026-11-22 11:28, was still written by the old code with only `file / lines / note`, so it still renders today.
7. **Why CI did not catch it**: existing unit tests use only the legacy shape (`file / lines / note`) as the read fixture and never feed the writer's real `_stored_patch()` output into the step 6 projection; the contract test only checks the OpenAPI shape, not the end-to-end "stored → read" shape.

### Responsibility boundary

- This is not an AI clustering degradation, evaluation, push or git failure: the event log and terminal result show those steps succeeded.
- This is not a "historical data migration" problem: old turns remain valid; the current written shape is simply not accepted by the current read model.
- This is not merely a frontend error-code granularity problem (though it amplifies the undiagnosability): changing only the error code would not make step 6 show content.

## Recommended solution (the only one)

**Change step 6's read contract from "validate the raw stored dictionary" to "project the current bundle", and render multi-file patches.**

Specifically:

1. **API read model**: change `StepRoundPatch` from `{file, lines, note?}` to `{files: [{file, lines, overwrite}], note?}`; `_round_item()` no longer does `model_validate(raw patch)` but reuses `_stored_bundle()` (extract it into a shared helper if needed) to normalize both historical shapes into a bundle (the legacy single file becomes one item in `files`), then projects it explicitly into the DTO. A later stored field then cannot break the read path.
2. **Contract and design doc**: run `pnpm contract:generate` to update `packages/contracts`, and change the `patch` example in `plans/fullstack-design/05-api-design.md` §3.6 to `files[]` (keep the single-file example to document legacy compatibility).
3. **Frontend rendering**: `StepIterations.vue#L215-L221` passes `round.patch` to `DiffView`; `DiffView.vue` renders one block per item in `files`, each showing its path header (matching the prototype's "生成的 edit patch" block). A single-file patch looks exactly like today.
4. **Regression tests**: add API tests that build one-file and two-file turns with `_stored_patch()` and assert `steps/iteration` returns 200 with the right `patch.files` count and content; keep one legacy `{file, lines, note}` case. Add a bundle-shaped run fixture to E2E and assert step 6 renders every file path and the patch content; the evaluation comparison and commit card stay covered by the existing step-6 test.
5. **Agent Note**: record "the read model must project the stored bundle; never validate a stored dictionary with a forbid-extra model" under `.agents/notes/implemented/bug-fix/`.

Two alternatives are not recommended: catching the exception and returning `patch: null`, or opening `extra="ignore"` on `StepRoundPatch`. The former removes the patch preview from the turn card even though the patch is step 6's core information; the latter still lacks `file / lines` for a real multi-file bundle. Both merely turn the 500 into silently missing content and do not address the root cause.

## Implementation

- `apps/api/app/service/evolution/stages.py`: `StepRoundPatch` becomes a bundle projection; `_round_item()` reuses `_stored_bundle()`.
- `packages/contracts`: regenerate the OpenAPI types.
- `apps/web/src/pages/evolution/components/DiffView.vue`: multi-file rendering; `StepIterations.vue` keeps passing `round.patch` through unchanged.
- `apps/api/tests/evolution/`, `tests/e2e/`: writer → reader regression.
- `plans/fullstack-design/05-api-design.md`, Agent Note.

## Implementation steps

1. Change the DTO and the `_round_item()` projection; first make the projection unit tests pass for both shapes.
2. Add API regression tests using the real `_stored_patch()` output; confirm the old implementation fails and the new one passes.
3. Update the frontend and contract, generate `api.d.ts`.
4. Add the E2E scenario and design doc, run the gates.
5. Post the fixed production step 6 screenshot and the old-run comparison to this issue.

## Dependencies and boundary

- Dependencies: `bugfix-02` (`#436` introduced the `overwrite` stored shape), `bugfix-21` (`#488` introduced the `files / intent / report` stored shape).
- Boundary: only the read projection, contract, rendering and tests; do not migrate historical data, do not change patch generation / evaluation / push logic, do not touch the run's final verdict.
- The production fix needs one deployment; after deploying, re-check this run and at least one historical run.

## Independent verification

Reproduction (read-only, admin required):

```sh
TOKEN=$(curl -s -X POST http://8.149.232.63/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<AI_EVAL_PASSWORD>"}' | jq -r .accessToken)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://8.149.232.63/api/workspaces/01M7KJ05ENF9784GPBDV544VB0/evolution/runs/01M834EBAY3C9BB3TM8V85VHQN/steps/iteration" \
  -w '\nHTTP %{http_code}\n'
```

- Now: `HTTP 500`, `{"error":{"code":"INTERNAL",...}}`.
- After the fix: `HTTP 200`, `payload.rounds[0].patch.files` has at least 1 item, and URL / title / evaluation / commit match the `final` step.
- Regression: step 6 of `01M80MSB72NFZNDKK2Q3YN991K` stays 200 and its patch still renders.

Local:

```sh
pnpm test:api -- tests/evolution/test_iteration_round_patch.py
pnpm test:e2e -- --pattern iteration
pnpm contract:check
pnpm verify:flow
```

- Expected: the new cases cover the bundle single-file, bundle multi-file and legacy single-file shapes; contract has no diff; flow passes.

## Acceptance

- [ ] The same production run shows turn cards at step 6: source bad cases, generated patch (with file paths), evaluation comparison and accepted commit, with no `EVOLUTION_RUN_STEP_UNAVAILABLE`.
- [ ] A historical run (e.g. `01M80MSB72NFZNDKK2Q3YN991K`) behaves and renders the same at step 6.
- [ ] The new API regression case fails before the fix, passes after it, and uses `_stored_patch()` output as input.
- [ ] A multi-file bundle renders one diff block per file at step 6, and the contract and design doc §3.6 are updated.
- [ ] The step 6 read path no longer applies forbid-extra validation to the stored dictionary.

## Gates and CI

- `pnpm verify:flow`, `pnpm test:gates`, `pnpm contract:check`
- `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`
- `pnpm lint:web`, `pnpm typecheck:web`, `pnpm test:web`, `pnpm test:e2e -- --pattern iteration`
- CI must run tests; coverage must stay at or above 80%.

## Non-goals

- Do not fix the run itself: it completed successfully and its final verdict is valid.
- Do not migrate or rewrite historical turn data.
- Do not change patch generation, agent edits, evaluation or push logic.
- Do not unify frontend error codes (for example distinguishing `INTERNAL` from `STEP_NOT_READY`); that can be a separate issue.
- Do not clean up this evidence release.
