# Edit submission validation rejects a valid multi-line insert_after anchor and fails the whole patch stage

English | [中文](bugfix-edit-insert-anchor-multiline.md)

```yaml flow
kind: issue
id: bugfix-57
milestone: bugfix
depends:
  - bugfix-46
priority: P2
status: in-progress
scope:
  - apps/api/app/third_party_api/ai_agent/edits.py
  - apps/api/app/service/evolution/patch_source.py
  - apps/api/app/third_party_api/ai_agent/attribution_case_tools.py
  - apps/api/tests/**
  - docs/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-25-edit-insert-anchor-multiline.md
github:
  number: 599
  url: https://github.com/Shadow-Azure/harness-evolution/issues/599
```

## Background

At 2026-11-25 09:29:41 (CST) the production full run `01M885592456VVK5B68DSMRKTE` (workspace `01M7KJ05ENF9784GPBDV544VB0`, target `codespec-subagent-driven-development@openspec-cn-main-copy-ar-a7ec200-claude-core`) started step 6/7, "Iteration". The first two candidates passed evaluation and were accepted; turn 3/10 failed outright during patch generation:

```text
status=failed
error.stage=patch
error.message=claude-code edit submission failed validation
at=2026-11-25T09:52:38+08:00
```

- Production page: `http://8.149.232.63/workspaces/01M7KJ05ENF9784GPBDV544VB0/evolution/runs/01M885592456VVK5B68DSMRKTE`
- Release running at failure: `/opt/harness/releases/d8c5d23f38c618e0aa80b33e84808567f528887a` (`d8c5d23f`, the merge commit of PR #591).

### Problem statement

The run's durable events (`GET /api/evolution/runs/{id}/events`) narrow the failure to one `agent.edit` call, and that call did not fail because the file was missing, unparsable, or because the tool surface lacked `Write`. It failed because **the submitted JSON5 document was parsed into an object and then rejected by Pydantic validation**:

| seq | event | key fields |
|---|---|---|
| 20 | `ai_agent_call` `agent.edit` ok (turn 2) | `outcome=ok`, tokens>0 |
| 21–27 | turn 2 candidate / push / eval / apply | candidate accepted by evaluation |
| 28 | `ai_agent_call` `agent.edit` **error** (turn 3) | `model=MiniMax-M3.1-Flash[1m]`, `latencyMs=200674`, `costUsd=1.482657`, `inputTokens=64634`, `outputTokens=36631`, `attempts=1`, `submissionRounds=1`, `submissionParsedBy=json5`, `submissionRepaired=false`, `submissionParseFailures=0`, `submissionValidationFailures=1`, `sessionId=null` |
| 29 | `run_failed` (candidate stage) | `type=ConfigError`, `detail` is only the same generic message |
| 30 | `run_failed` (step stage) | `detail` is only a Python traceback, still without the field-level validation reason |

Four common causes are ruled out up front:

1. **Not a parse failure**: `submissionParsedBy=json5`, `submissionParseFailures=0`, and `submissionRepaired=false` mean the JSON5 document was read and parsed into an object normally.
2. **Not a missing file or a denied write**: `submissionRounds=1` and validation actually reached Pydantic; a missing file produces `missing`, and a denied write carries a `permission denied:` detail. Neither is this path.
3. **Not an edit tool-surface regression**: the file was written, so `Write` was available; the `--tools` and `Edit(//<abs>)` rules fixed by bugfix-46 / PR #566 were effective in this call.
4. **Not a recent PR breaking edit globally**: on the same release and the same run, turns 1 and 2 `agent.edit` both returned `ok` and were accepted; only turn 3 failed.

One related boundary: if JSON5 parsing itself fails (all three tiers — strict JSON, JSON5, json-repair — fail), `submission.collect()` returns `invalid + parse_error`; the edit path still does not retry and terminates with `retryable=False`, while only analyze retries once through `feedback_prompt()`. For edit, a parse failure and a validation failure therefore share the same terminal state; only the detail differs.

The real reason lives in the submission file. After the call failed, `.harness-evolution/edits.json5` was still in the production workspace (20,628 bytes, not deleted). After retrieving it and replaying validation with **that release's own code and venv**, the field-level error is deterministic:

```text
edits.6: Value error, target must be a single-line substring
```

`edits.6` is the 0-based index, i.e. the **7th** edit in the plan: `op=insert_after`, `file=skills/codespec-subagent-driven-development/SKILL.md`, and `target` is the 4-line `### 验收与回归` template block (158 characters) that occurs exactly once in `SKILL.md`. The other 7 edits, the total of 8 edits (within `EDIT_BUDGET=8`), the file scope, every content line count (28 at most), the summary, and every rationale are all valid; **only this edit is rejected because its target spans lines**.

### Root-cause analysis process

1. **Confirm the failure class**: the `submission*` counters in `ai_agent_call` show "parsed, validation failed", not `missing` / parse failure / permission denial; `outcome=error`, `attempts=1`, and `sessionId=null` show that there was no second feedback turn.
2. **Follow the code path**: `ClaudeCodeProvider.edit_workspace()` (`apps/api/app/third_party_api/ai_agent/claude_code.py:403-476`) calls `self._submission.collect(prep, EditPlan.model_validate)` only once (`:442`); any non-ok outcome raises `claude-code edit submission failed validation` with `retryable=False` (`:456-464`), and it never calls `feedback_prompt()` for a retry the way analyze does (compare `:266-322`).
3. **Read the retained submission**: retrieve `.harness-evolution/edits.json5` from the workspace; parsing it with `json5` yields `{summary, edits}` with 8 edits, all targeting `skills/codespec-subagent-driven-development/SKILL.md`; every target occurs once in `SKILL.md`, every content is at most 28 lines, and everything is within `EDIT_BUDGET=8` and `MAX_CONTENT_LINES=400`.
4. **Replay with the release code**: under release `d8c5d23f`'s `api/` with `/opt/harness/shared/venv`, `EditPlan.model_validate()` fails deterministically with `edits.6: Value error, target must be a single-line substring`. The failure has nothing to do with model prose, stderr, the network, or the CLI version; it is the validator deterministically rejecting a multi-line `insert_after` target.
5. **Check where the contract comes from**: `EditOp._validate_op_fields()` (`edits.py:158-179`) explicitly rejects a target containing `\n` / `\r` on the `insert_after` branch (`:171-172`), and `_apply_one()` (`:482-527`) carries the same check (`:503`). Yet the `EditOp` docstring (`:157-164`) says "the retry prompt gets a field-level message", while the edit path has no retry prompt at all. Design 07 §5.5.4 and flow issue bugfix-20 (#494) only require the anchor to "exist and be unique"; neither says "single line". The prompt the model receives, `_edit_prompt()` (`apps/api/app/service/evolution/patch_source.py:511-558`), only says "file must be inside the allowed scope; the anchor text must exist and be unique", and the derived JSON Schema cannot express a conditional "target must not contain a newline". In other words, **the model followed the contract it was told (a unique anchor), while the validator enforced a stricter rule that was never published and contradicts the design document**.
6. **Check whether a recent PR introduced it**:
   - The failing release `d8c5d23f` is the merge commit of PR #591 (`fix(evolution): cluster by attribution conclusions`); its diff touches clustering / prepare / stages plus tests and docs, not `edits.py`, `claude_code.py`, or `patch_source.py`.
   - The most recent change to the edit channel is PR #572 (`64fffe72`, 2026-11-24); it only changes `claude_code.py` plus its tests/docs (headless argv / tool surface / failure evidence), not `edits.py` or the edit prompt. It is already part of `d8c5d23f`, and it is exactly what lets edit write the submission file at all.
   - The rule "insert_after target must be single-line" was added by PR #494 (`d1accc70`, 2026-11-23), before both #572 and #591; every release since then carried it. Strictly speaking, if "recent" includes #494 from 11-23, the rule does come from a relatively recent merge; but it is the **source of the rule**, not a regression from the latest edit fix or the failing release.
   - #591 changed the cluster text fed into the edit prompt (cluster titles moved from bad-case titles to attribution conclusions), and this turn-3 cluster happens to target "missing blocking verification gates and regression-failure grading evidence", which may have influenced the concrete edit shape the model chose; but #591 did not change the validation rules in `edits.py`, so it cannot explain why a multi-line `insert_after` is necessarily rejected.
   - Rounds 1 and 2 succeed and turn 3 fails on the same release, which matches per-call model-output variance, not a deployment-wide regression.
7. **Explain why only the generic error is visible**: `AgentProviderError.detail` already contains `validation failed: edits.6: ...` (`_submission_detail()`, `claude_code.py:1222-1228`), but when `retryable=False`, `GitCandidateService._handle_provider_failure()` forwards `ConfigError(sanitize_message(str(error)))` to `_fail_patch_generation()` (`git_candidate.py:760-775`); `str(error)` is only the message, so the detail is dropped. The run's `error` and the job's `error` therefore retain only `claude-code edit submission failed validation`, and the field-level reason survives only in the written `edits.json5` and this reproduction.

### Conclusion

- **Immediate cause**: edit 7 of the plan is an `insert_after` whose target is a 4-line text block; the `insert_after` branch of `EditOp` requires a single-line target, so `EditPlan.model_validate()` raises `edits.6: Value error, target must be a single-line substring`, `edit_workspace()` fails with `retryable=False`, patch generation produces no candidate, and the whole run fails.
- **Root cause**: the `insert_after` anchor contract is inconsistent between "the contract visible to the model" and "the contract the validator actually enforces". The prompt, the derived JSON Schema, and design 07 §5.5.4 all say only "the anchor text exists and is unique"; the validator additionally requires "single line", and that rule appears in neither the prompt nor the schema. The 4-line block in the plan is the unique, legitimate text block, and the model even wrote in its summary that all target anchors were checked for uniqueness, which shows it did the right thing according to the visible contract. Edit is a single-shot call and a validation failure is not retried, so this hidden constraint terminates the entire turn.
- **Was it caused by a recently merged PR? It is not a regression from the latest deployment or the latest edit fix, but the single-line rule does come from #494 on 11-23.** PR #591 did not change edit validation; it only changed the cluster text, which may have influenced the concrete edit shape chosen here. PR #572 is the fix that enables edit submission, not the cause. The "single line" rule comes from the earlier #494, whose comment assumes "the field-level error reaches the retry prompt", while edit has no retry. Rounds 1 and 2 succeeding on the same release also rules out "a recent change broke edit globally".
- **Why turns 1 and 2 succeeded and turn 3 failed**: the first two plans contained no multi-line `insert_after`; the third used a natural, unique, but multi-line block anchor, which triggered the hidden rule. This is not a seed or deployment difference; it is a single-point contract mismatch caused by per-call model variance.
- **Observability gap (does not change the root cause)**: the field-level `detail` is dropped when converting to `ConfigError`, so the run page and the job show only the generic message; this analysis obtained `edits.6` by reading the retained `edits.json5` and replaying the release code. This is an observability gap, not the cause of this failure, and the recommended solution below does not depend on fixing it.

## Goals

- Make the `insert_after` anchor contract match the contract visible to the model: any text fragment that **exists and is unique** in the file is a valid anchor, including a multi-line block; target no longer has to be a single line.
- Make the applier insert content **after the last line** of the matched block while preserving determinism and all uniqueness, scope, content, and budget limits; the output for a single-line target must be byte-for-byte identical to today's.
- Synchronize the prompt, the derived-schema explanation, the design document, and the tests to one contract, removing the structural gap of "a rule that exists only in the validator".
- Use the production plan shape as a regression: with the same 8 edits and the same 4-line block anchor, `EditPlan.model_validate()` must pass and `apply_edit_plan()` must change only `SKILL.md` and report every edit as `applied`.
- Do not change edit's single-shot call model (no feedback retry), the tool surface, `EDIT_BUDGET`, `MAX_CONTENT_LINES`, or the timeouts.

## Design authority

- [07 §5.5.4 Instruction-style EditPlan patch](../../../plans/fullstack-design/07-backend-implementation.md): the EditPlan contract, `insert_after` line boundary, deterministic application, and safety gates; that section's anchor rule is only "exists and is unique".
- [07 §5.5.3 Six-layer JSON reliability](../../../plans/fullstack-design/07-backend-implementation.md): Pydantic is the single source of truth for submission validation and the schema is derived from the model; the caller prompt must state any semantic constraint the schema cannot express.
- [bugfix-20 / #494](https://github.com/Shadow-Azure/harness-evolution/issues/494): the original EditPlan applier contract and the acceptance rule "anchor exists and is unique".
- [bugfix-46 / #566](https://github.com/Shadow-Azure/harness-evolution/issues/566): the fix that restored edit submission on the real CLI; this issue addresses the next contract layer exposed after that fix.
- [06 §4 / 07 §5.5.3 failure observability](../../../plans/fullstack-design/07-backend-implementation.md): `AgentProviderError.detail` is the carrier for field-level details; this failure lost it in the `ConfigError` conversion, recorded here as an observability gap and left out of this solution's scope.

## Implementation

**The single recommended solution: unify the `insert_after` anchor to "an existing and unique text block", allow it to span lines, define the insertion point as after the block's last line, and synchronize the prompt, applier, tests, and design document.**

1. **Relax model validation**: delete the `insert_after` rejection of `\n` / `\r` in `EditOp._validate_op_fields()` (`edits.py:171-172`), while keeping the non-blank target, the `append` no-target rule, the `delete` no-content rule, and every other content/scope/budget constraint. Change the `EditOp` docstring to "the `insert_after` target is a text fragment that occurs once in the file and may span lines".
2. **Locate by block in the applier**: `_apply_one()` (`edits.py:482-527`) and `_insert_after_text()` (`:467-480`) must stop locating the anchor with "a line contains target" and instead:
   - match the whole target text across the file and require exactly one occurrence (reuse `_apply_one`'s existing `text.count(target)` and its ambiguous/missing branches);
   - find the line containing the target's last character; if the target itself ends with a newline, use the position after that newline;
   - insert content lines after that line using the line's existing newline style (`\n` or `\r\n`);
   - keep the single-line target output byte-for-byte identical to the current implementation (existing cases such as `test_insert_after_last_line_without_newline` must keep passing).
3. **Put the contract into the prompt**: extend `_edit_prompt()` (`patch_source.py:511-558`) from "the anchor text must exist and be unique" to "target is a text fragment that occurs once in the file and may span lines; `insert_after` inserts content after the fragment's last line". This is the positive contract the model sees, instead of making it guess "single line".
4. **Synchronize the design document**: in the execution-flow bullet of 07 §5.5.4, state that "the anchor may be a single-line or multi-line text block; `insert_after` inserts after the block's last line", and update the corresponding `plans/` text.
5. **Add regression tests**: remove/rewrite `test_insert_after_rejects_a_multiline_anchor_at_model_construction` (`apps/api/tests/test_edit_plan_applier.py:377-380`) and add:
   - a unique 4-line block anchor passes model validation and, after application, inserts after the block's last line;
   - a single-line anchor produces exactly the same output as the old implementation;
   - a multi-line block occurring 0 times becomes `skipped_anchor_missing`, and occurring twice becomes `error` (ambiguous);
   - a multi-line block in a CRLF file preserves `\r\n` on insertion;
   - `append` / `replace` / `delete` semantics are unchanged.
6. **Do not change observability or retries**: `feedback_prompt()` and the single-shot structure of `edit_workspace()` stay as they are; the `ConfigError` conversion that drops detail is not part of this solution, to avoid expanding the fix into the run error model.

### Incidental fix (a regression already red on main)

#588 (`744f4f57`) added the required `--conclusion` / `--root-cause` arguments to `attribute-badcases/make_probe_report.py` and updated `SKILL.md` to require an explicit verdict; but the platform MCP tool `CaseTools.write_probe_report(report: ReportFields)` had neither field on `ReportFields` (`extra="forbid"`) nor forwarded them, so every attribution report in `case-tools` mode was rejected by the script, `unit-tests-api` went red, and main's own CI was a failure. This PR adds the two required fields (verdict enum + non-blank root-cause validator) in `attribution_case_tools.py` and updates the `selected_target` fixture and assertions in `test_case_tools.py`; without it no PR can pass CI. The fix does not change anchor semantics, budgets, or retry boundaries.

## Implementation steps

1. First add a failing regression: pass an `insert_after` plan with a synthetic 4-line block anchor to `EditPlan.model_validate()` and confirm the current implementation reports `target must be a single-line substring`.
2. Remove the validator's single-line rejection and rewrite `_insert_after_text()` and the `insert_after` branch of `_apply_one()` as "whole unique match + insert after the block's last line"; keep the single-line path byte-for-byte unchanged.
3. Update the anchor description in `_edit_prompt()` and the design text in 07 §5.5.4 / `plans/`.
4. Update/add unit tests covering the single-line regression, multi-line blocks, CRLF, missing and ambiguous anchors; run `pnpm test:api -- tests/test_edit_plan_applier.py` and `tests/test_ai_agent_claude_code.py`.
5. Replay end to end with a safe copy of the production plan (keep only the summary structure, the 4-line block target, and the content line counts; do not write the production text into the repo): `EditPlan.model_validate()` passes, `apply_edit_plan()` changes only `SKILL.md`, and all 8 reports are `applied`.
6. After deployment, start a new full run and verify at step 6 turn 3 that `agent.edit` is `ok` and the run proceeds to candidate / push / eval; the implementation PR adds an Agent Note in the same commit and backfills this issue's `adr`.

## Dependencies and boundary

- Depends on bugfix-46 (#566, the edit tool surface is fixed and merged; this issue addresses the submission contract after it).
- Only change `EditOp` / `_apply_one` / `_insert_after_text` in `edits.py`, `_edit_prompt()` in `patch_source.py`, the corresponding tests, `docs/**`, `plans/**`, and `.agents/**`.
- Do not change the tool surface, permission rules, timeouts, or retries in `claude_code.py` / `submission.py`; do not change `EDIT_BUDGET`, `MAX_CONTENT_LINES`, or `allowed_paths`; do not change clustering, attribution, evaluation, or the frontend.
- Do not write production plan text, Session content, screenshots, or credentials into the repository; this issue and the implementation PR only reference bounded error strings and synthetic samples.

## Verification

```sh
pnpm test:api -- tests/test_edit_plan_applier.py
pnpm test:api -- tests/test_ai_agent_claude_code.py
pnpm lint:api
pnpm typecheck:api
pnpm verify:flow
```

- A synthetic 4-line block anchor passes `EditPlan.model_validate()`, the application report is `applied`, and the content appears after the block's last line.
- All existing single-line `insert_after` assertions remain byte-for-byte identical; a multi-line block occurring 0 times becomes `skipped_anchor_missing`, and occurring twice becomes `error` (`anchor is ambiguous`).
- Production plan shape replay: all 8 edits are `applied`, only `skills/codespec-subagent-driven-development/SKILL.md` changes, and `edits.6` no longer reports `single-line substring`.
- A new production run's turn 3 `agent.edit` is `outcome=ok` with tokens>0 and `submissionValidationFailures=0`, and the run proceeds to candidate/push/eval.

## Acceptance

- `insert_after` accepts a multi-line text block that occurs once in the file; content is inserted after the block's last line, and the result is deterministic and replayable.
- The same production plan shape no longer triggers `target must be a single-line substring`; `edits.6` validates.
- Single-line `insert_after` behavior is byte-for-byte identical to today; missing anchors, ambiguous anchors, out-of-scope files, oversized content, and over-budget plans are still rejected or skipped under the existing rules.
- The prompt, the derived-schema explanation, 07 §5.5.4, and the validator express the same anchor contract; no hidden rule remains only in code.
- One real full run completes the previously failing turn 3 and proceeds to candidate / push / eval.
- The repository gains no production credentials, Session content, or plan text.

## Gates and CI

- `pnpm test:api` (at least `tests/test_edit_plan_applier.py`, `tests/test_ai_agent_claude_code.py`), `pnpm lint:api`, `pnpm typecheck:api`.
- `pnpm verify:flow`, `pnpm verify:flow-online`, `pnpm lint:docs`.
- CI lanes: `api-static`, `unit-tests-api`, `docs-flow`, `flow-online`.
- The implementation PR title and commits must contain this issue number; the same PR adds an Agent Note and backfills `adr`.

## Non-goals

- Do not add a feedback retry to edit, and do not change agent-edit's single-shot / fail-fast semantics.
- Do not relax anchor uniqueness, file scope, content line limits, or the 8-edit budget; do not let a multi-line target bypass the uniqueness check.
- Do not change `--tools` / permission rules / `EDIT_TIMEOUT_SECONDS` / `EDIT_MAX_TURNS` in `claude_code.py`.
- Do not change parsing, schema derivation, or the `feedback_prompt()` contract in `submission.py`; do not change the analyze path.
- Do not fold the "ConfigError drops detail" observability gap into this solution; it does not affect this root cause or the fix's acceptance.
- Do not change clustering, attribution, the evaluation gateway, the frontend, or the deployment flow.
