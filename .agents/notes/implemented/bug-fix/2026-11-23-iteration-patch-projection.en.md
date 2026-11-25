# Agent Note: Project the stored patch bundle in step 6

Status: implemented

English | [中文](2026-11-23-iteration-patch-projection.md)

## Problem

Run-detail step 6 handed the database `round.patch` straight to `StepRoundPatch.model_validate()`, while the read model only had `file / lines / note` and inherited `extra="forbid"` from `IdentityModel`. The write side had already grown twice: `#436` added `overwrite` for pause/resume, and `#488` added `files[] / intent / report` for agent edits, merging the legacy `file / lines / overwrite` for a single file. The newest run's patch dictionary therefore had 4 extra keys, reading raised `extra_forbidden`, the exception bubbled up as a 500 `INTERNAL`, and the frontend rendered every non-`STEP_NOT_READY` error as `EVOLUTION_RUN_STEP_UNAVAILABLE`. In production the whole "what changed, how much the evaluation improved, and what the commit is" block of the latest run was invisible.

The same contract was written twice: the write side's `_stored_patch()` defined the stored shape, and the read side guessed that shape with a closed model. The legacy single-file case passed tests, but multi-file patches and the new audit fields never entered the read path, so CI stayed green.

Restoring a 200 exposed a second contract gap: an agent-edit turn's `files[].lines` is the **whole file**, yet `DiffView.vue` still colored it by the leading `+` / `-` / `@@`. On 2026-11-25, turn 4 of production run `01M8957ATHZX4K48K9PGXSVSVK` therefore rendered 147 lines of Markdown bullets and `---` out of a 478-line whole file as red deletions, while the real diff (72 added, 0 deleted) existed only in the `candidate_committed` event. `intent`, `report`, and the candidate's real `unified_diff` all existed but never reached the step-6 read model.

## Decision

- Move "stored dictionary → `PatchBundle`" restoration from `git_candidate.py` into `round_patch.py` as `stored_bundle()`, shared by the write and read sides; the read side no longer validates the raw dictionary.
- `StepRoundPatch` becomes `{files: [{file, lines, overwrite}], note?, diff?}`; `_round_item()` restores the bundle first and then projects it explicitly into the DTO. `note` is read only from the raw dictionary and stays `null` when missing or blank, matching legacy semantics. A patch that cannot be restored returns `patch: null` instead of throwing from the read chain.
- After a candidate commit succeeds, the write side stores `CandidateWorkspace.unified_diff` in `round.patch.diff`; `PatchBundle.unified_diff` carries only this post-commit git truth and a patch source never fills it early. `stored_bundle()` reads `diff` back, and `_round_patch()` splits it into lines.
- When a historical turn has no stored `diff`, the read side synthesizes `-` / `+` / `@@` change blocks from `intent` edits whose `report.status == "applied"`; with no applied edit or no intent, `diff` is `null`. Neither path treats `files[].lines` as a diff.
- `DiffView.vue` becomes diff-first: split file blocks on `diff --git`, mark `@@` as hunks, color content lines by `+` / `-`, and keep `index` / `---` / `+++` file-header lines out of the add/delete counts; with `diff: null`, show the neutral whole-file preview and state that lines are not colored.
- A multi-file bundle projects in `files[]` order, and a single-file bundle and the historical `{file, lines, note}` both normalize to one `files` item; `files[]` is only the no-diff whole-file preview and no longer carries diff semantics.
- Regression tests build one-file, two-file and legacy turns from the real `_stored_patch()` output and assert `steps/iteration` returns 200 with the right `patch.files`; additional cases cover the real-diff write/read cycle, a historical turn synthesized from applied/skipped edits, and the `null` turn with neither diff nor intent. The E2E fixture's accepted turn carries a real diff, and the historical turn asserts a neutral preview with zero red deletion lines.

## Alternatives considered

- **Swallow the validation error into `patch: null` with `try/except`**: rejected. It removes the 500 but step 6 loses the patch preview, which is that step's core information; it turns an error into silently missing content.
- **Open `extra="ignore"` on `StepRoundPatch`**: rejected. Current single-file runs would pass, but a multi-file bundle still lacks the required `file / lines`, so agent-edit turns keep returning 500; it only extends the old shape's life without establishing a projection boundary.
- **Duplicate the normalization logic on the read side**: rejected. Keeping separate `files`/legacy parsers on the write and read sides is exactly how this contract drifted; sharing `stored_bundle()` leaves one place to adapt on the next upgrade.
- **Change only the frontend error code or error-card copy**: rejected. Error-code granularity can be its own issue, but it does not make step 6 show turn content.
- **Keep coloring `files[].lines` after checking `overwrite`**: rejected. `overwrite` only describes how bytes were written; a whole file's `-` / `---` cannot be distinguished from a real removal at the byte level, and continuing to color it is exactly this false-positive root cause.
- **Let the frontend guess a diff from the whole file or strip file headers**: rejected. Without the previous revision the guessed diff would fabricate changes; git already produced the real diff on the candidate, so there is no reason to recompute it.
- **Only switch historical turns to the neutral preview without persisting a new diff**: rejected. The false positives disappear, but new turns still cannot show the real change and the intent-vs-diff audit stays lost.
- **Migrate historical turns to one new shape**: rejected. Old rows have always been valid and the read side should stay compatible; migration widens the change surface and adds one-off data risk.

## Consequences

- Step 6 returns 200 for the current multi-file bundle, the single-file bundle and the historical legacy shape; a fourth, unrestorable shape degrades to `patch: null` while the other turn fields still render. When the stored shape gains a field the read model does not use, the whole step no longer fails on `extra="forbid"`.
- `round_patch.py` becomes the shared write/read restoration seam: `git_candidate._patch_file/_patch_note/_patch_hash` and `stages._round_patch()` all take their facts from `stored_bundle()`, so a later storage change only touches this module.
- An unrestorable patch now degrades to `patch: null` while the rest of the turn card still renders. The API regression test covers that shape; the read path adds no warning log yet, so the visible signal is a missing patch preview.
- `packages/contracts` and `05 §3.6` now use `files[]`; clients that read the old `patch.file` must read `files[0]`. The repository has only one consumer of this DTO, `DiffView.vue`, and it is updated; `DiffView` also falls back to an empty list when `files` is absent, so a rolling deploy window cannot throw during render.
- A new turn's `patch.diff` comes straight from the candidate commit's real git diff, and the page colors only content lines while file headers and metadata stay out of the add/delete counts; historical turns use change blocks synthesized from applied edits, and fall back to the neutral whole-file preview when no usable data exists, so red deletion false positives are gone.
- `patch.diff` is not truncated in storage or in the response (event payloads still truncate at 20k characters), so a whole-file-overwrite turn stores one extra copy of the diff; that is the cost of keeping a truthful audit surface where the page and `candidate_committed` no longer disagree.
- Production verification needs one deployment; this issue does not migrate data, change patch generation/evaluation/push logic, or unify frontend error codes.
