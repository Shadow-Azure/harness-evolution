# Agent Note: Launch-wizard step 2 clamps Session titles and keeps four columns visible

Status: implemented

English | [中文](2026-11-19-launch-wizard-session-title-clamp.md)

## Problem

Step 2 of "Start self-evolution" rendered `session_families.title` directly as the Session title. For SWE-bench-style sessions the first prompt is the whole task description, so the production table widened and pushed "object appears", "object trigger time", and "bad case count" out of the modal, leaving the user unable to check the association evidence.

The Session list already displays `short` (`session_families.short_title`, the first 120 characters) with an ellipsis, but `preview/sessions` only returned the full `title`, so step 2 could not use that existing field. The table also combined `white-space: nowrap` with no width bound, so long content directly participated in table sizing.

## Decision

`SessionPreviewItem` gains `short`, taken from `SessionRecord.short_title`; `title` keeps returning the full title. The frontend renders `short || title` as a single-line ellipsized Session label and exposes the full title through the `title` attribute; the short Session ID stays.

The step 2 Session table becomes a fixed layout with a 38% title column, 15% appearance column, 22% trigger column, and 25% bad-case-count column, and its headers may wrap. A long title is clipped inside the title column instead of resizing the others. The `.rep-scroll` horizontal scroll remains as a narrow-viewport fallback; at a 1440-wide viewport and the 720-wide modal all four columns fit.

Association logic, bad case statistics, paging, and ordering are unchanged; `short_title` generation stays as the first 120 characters of the title.

## Alternatives considered

- **Clamp the full `title` in the frontend only**: it fixes the overflow but still ships the whole prompt to the browser and ignores the short-title field the Session list already has, leaving the contract gap to be filled later. Rejected.
- **Change how `short_title` is generated**: it would change the Session list, search, and other consumers beyond this display defect. Rejected.
- **Two-line title clamp**: it shows a bit more text but makes row height content-dependent and diverges from the prototype's single-line table; one line plus a tooltip already lets users distinguish rows and read the whole title. Rejected.
- **Show the full UUID in the Session column**: the prototype does, but it widens the Session column and is a separate product decision; this fix keeps the head/tail abbreviated ID. Rejected.

## Consequences

- The preview response carries `short` (within 120 characters) and the full `title`; the full title may still be long but only appears in the hover tooltip.
- `short_title` remains "first 120 characters of the title", not a semantic summary; a SWE-bench row still shows a prompt prefix, merely clipped and hoverable.
- The new `SessionPreviewItem` field is required, so all generated contracts and consumers are updated together; an older server response without `short` falls back to `title` in the frontend.
- A fixed layout compresses the title column at very narrow viewports and relies on `.rep-scroll`; the acceptance target is the 720-wide modal at a 1440-wide viewport.
