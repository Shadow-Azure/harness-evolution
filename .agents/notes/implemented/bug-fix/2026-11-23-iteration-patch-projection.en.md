# Agent Note: Project the stored patch bundle in step 6

Status: implemented

English | [中文](2026-11-23-iteration-patch-projection.md)

## Problem

Run-detail step 6 handed the database `round.patch` straight to `StepRoundPatch.model_validate()`, while the read model only had `file / lines / note` and inherited `extra="forbid"` from `IdentityModel`. The write side had already grown twice: `#436` added `overwrite` for pause/resume, and `#488` added `files[] / intent / report` for agent edits, merging the legacy `file / lines / overwrite` for a single file. The newest run's patch dictionary therefore had 4 extra keys, reading raised `extra_forbidden`, the exception bubbled up as a 500 `INTERNAL`, and the frontend rendered every non-`STEP_NOT_READY` error as `EVOLUTION_RUN_STEP_UNAVAILABLE`. In production the whole "what changed, how much the evaluation improved, and what the commit is" block of the latest run was invisible.

The same contract was written twice: the write side's `_stored_patch()` defined the stored shape, and the read side guessed that shape with a closed model. The legacy single-file case passed tests, but multi-file patches and the new audit fields never entered the read path, so CI stayed green.

## Decision

- Move "stored dictionary → `PatchBundle`" restoration from `git_candidate.py` into `round_patch.py` as `stored_bundle()`, shared by the write and read sides; the read side no longer validates the raw dictionary.
- `StepRoundPatch` becomes `{files: [{file, lines, overwrite}], note?}`; `_round_item()` restores the bundle first and then projects it explicitly into the DTO. `note` is read only from the raw dictionary and stays `null` when missing or blank, matching legacy semantics. A patch that cannot be restored returns `patch: null` instead of throwing from the read chain.
- A multi-file bundle projects in `files[]` order; a single-file bundle and the historical `{file, lines, note}` both normalize to one `files` item. `overwrite` enters the read model, but this issue adds no mode label to the UI.
- `DiffView.vue` renders one path header and diff line set per item in `files`; the single-file visual is unchanged and multi-file patches get a separator between files. The `patch` example in `05 §3.6` now uses `files[]` and documents legacy compatibility.
- Regression tests build one-file, two-file and legacy turns from the real `_stored_patch()` output and assert `steps/iteration` returns 200 with the right `patch.files`; the E2E fixture's accepted turn becomes a two-file bundle and its step-6 smoke asserts both path headers and added/deleted lines are visible.

## Alternatives considered

- **Swallow the validation error into `patch: null` with `try/except`**: rejected. It removes the 500 but step 6 loses the patch preview, which is that step's core information; it turns an error into silently missing content.
- **Open `extra="ignore"` on `StepRoundPatch`**: rejected. Current single-file runs would pass, but a multi-file bundle still lacks the required `file / lines`, so agent-edit turns keep returning 500; it only extends the old shape's life without establishing a projection boundary.
- **Duplicate the normalization logic on the read side**: rejected. Keeping separate `files`/legacy parsers on the write and read sides is exactly how this contract drifted; sharing `stored_bundle()` leaves one place to adapt on the next upgrade.
- **Change only the frontend error code or error-card copy**: rejected. Error-code granularity can be its own issue, but it does not make step 6 show turn content.
- **Migrate historical turns to one new shape**: rejected. Old rows have always been valid and the read side should stay compatible; migration widens the change surface and adds one-off data risk.

## Consequences

- Step 6 returns 200 for the current multi-file bundle, the single-file bundle and the historical legacy shape; a fourth, unrestorable shape degrades to `patch: null` while the other turn fields still render. When the stored shape gains a field the read model does not use, the whole step no longer fails on `extra="forbid"`.
- `round_patch.py` becomes the shared write/read restoration seam: `git_candidate._patch_file/_patch_note/_patch_hash` and `stages._round_patch()` all take their facts from `stored_bundle()`, so a later storage change only touches this module.
- An unrestorable patch now degrades to `patch: null` while the rest of the turn card still renders. The API regression test covers that shape; the read path adds no warning log yet, so the visible signal is a missing patch preview.
- `packages/contracts` and `05 §3.6` now use `files[]`; clients that read the old `patch.file` must read `files[0]`. The repository has only one consumer of this DTO, `DiffView.vue`, and it is updated; `DiffView` also falls back to an empty list when `files` is absent, so a rolling deploy window cannot throw during render.
- Production verification needs one deployment; this issue does not migrate data, change patch generation/evaluation/push logic, or unify frontend error codes.
