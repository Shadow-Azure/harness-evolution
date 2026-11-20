# Agent Note: Short Session labels and fixed columns in run detail step 2

Status: implemented

English | [中文](2026-11-20-run-detail-session-short-title.md)

## Problem

「Evolution → run detail → step 2 Session association」rendered `sessionRows[].title` verbatim as the Session cell title. A Session's `title` is by design the first user prompt in full; the SWE-bench sample is a 3337-character task prompt. At 1500×837 it grew the first row to 329px and the Session column to 1247px, squeezing `object trigger / bad case / potential bad case` to 43–79px. The association evidence became unreadable, and two Sessions were indistinguishable apart from their IDs. The production/prototype comparison and root cause are in GitHub #440.

The short-label data already existed: `session_families.short_title` and the association result `AssociatedSession.short` both carried a value. But the prepare stage persisted only `sessionId/title/objectTriggerAt/badCaseCount` into `stats.sessionRows`, and the `StepSessionRow` contract had no `short`, so the frontend could only receive the full title. The presentation layer used automatic layout with wrapping cells, so the long prompt also took part in width calculation. Launch wizard step 2 (#404) had already been fixed with the same「short label + full-title hover + fixed column widths」approach; run detail's data path was not covered.

## Decision

- Complete the data path: the prepare stage writes `AssociatedSession.short` into `stats.sessionRows[].short`; `StepSessionRow` gains a nullable `short` that `steps/sessions` returns unchanged. When a historical run's persisted row has no `short`, the read path falls back to `title[:120]`, so old runs never need re-preparing.
- Constrain presentation: `StepSessions.vue` renders `row.short || row.title || "未命名 Session"` and keeps the full `title` in a `title` attribute; the label is ellipsized to one line. The table switches to `table-layout: fixed`, with a `colgroup` fixing the trigger column at 220px and both count columns at 130px, while keeping horizontal scroll on narrow containers (`min-width: 680px`).
- Keep four columns and existing semantics: do not add the prototype's extra「object appearance」column, and do not change the association algorithm, bad case statistics, pagination/ordering, or Session ID format.
- Cover three layers of regression: API tests assert the prepare stage persists `short`, the step API returns it, and historical rows fall back; a component test uses an over-long title to assert the visible short label and full hover text; a real-browser E2E asserts the first row height stays bounded, the Session column does not dominate, all four headers keep a real width, and the table does not overflow horizontally.

## Alternatives considered

- **Truncate `row.title` in the frontend only**: it bounds the height but shows a prompt prefix instead of the short label already available in the data, and duplicates the 120-character truncation rule in the client while the data path stays incomplete. Rejected.
- **Keep the full title and clamp to two lines**: the row would still grow with a long prompt, and automatic layout would still let a long unbreakable string influence column widths. The issue asks for a single/two-line row and four columns on screen; a single line fed by the short label is more direct. Rejected.
- **Add only a `max-width` and keep automatic layout**: a long title can still expand the column and the widths stay unstable. Only fixed layout guarantees the three evidence columns are not squeezed out. Rejected.
- **Re-prepare historical runs to backfill `short`**: expensive and unnecessary; the read-side `title[:120]` fallback already renders existing runs, and only new runs need the real `short_title`. Rejected.
- **Add the prototype's extra「object appearance」column**: the column-scope difference is not this issue's root cause and would change the table's information architecture; it is left to a separate design decision. Rejected.

## Consequences

- At 1440/1500-wide viewports step 2 shows all four columns; an over-long prompt keeps the Session row at single-line height, and the full title remains available on hover. Associated Session counts, pagination, ordering, and skipped statistics are unchanged.
- New runs take their short label from `session_families.short_title`; historical runs fall back to `title[:120]`, which may still be a prompt prefix. A truly semantic title needs a separate issue to extract it upstream or from the first prompt.
- `StepSessionRow` gains an optional field, so the API stays backward compatible; `openapi.json` and the generated types come from `pnpm contract:generate`.
- The E2E fixture uses a synthetic 3337-character prompt to verify layout and never reads or commits production Session content.
