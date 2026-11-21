# Agent Note: Step-4 attribution report links

Status: implemented

English | [中文](2026-11-20-attribution-report-link.md)

## Problem

The run detail rendered both the step-4 "attribution report ID" and "source bad case" as plain text. The V2 prototype designs them as new-window links: the report ID opens the bad case's error detail on the "attribution analysis" tab, and the source bad case opens the "problem description" tab. Production matches `main`, so this is not a build or cache issue. Production measurements and the prototype comparison are in [#443](https://github.com/Shadow-Azure/harness-evolution/issues/443).

Changing only the template could not fix it: the error-detail deep link requires a Session, and the step-4 DTO (`StepAttributionRow`) exposes `bad_case_id` / `attribution_id` but no Session. The design document recorded the step-4 columns but not the click behaviour, and the component test asserted only text and counts, so the prototype interaction was lost without a red test.

## Decision

- `StepAttributionRow` gains a required `session_id`. V2 uses `candidate.session_id` and legacy uses `first.probe_session_id`; both are the real source Session and are not inferred from other steps.
- `StepAttribution.vue` receives `wid` and renders both columns with `badCaseDeepLink(wid, row.sessionId, row.badCaseId, tab, attributionId)`: the source bad case uses `tab=desc`, and the report ID uses `tab=attr` with `at=row.attributionId`. Anchors use `target="_blank"` and `rel="noopener noreferrer"`, keep the full ID as visible text, and add `title` and `aria-label`.
- `RunStepContent.vue` passes its existing `wid` to `StepAttribution`; no new context or request is introduced.
- Component tests lock `href` / `target` / `rel` / `aria-label` for both columns; an API stage test locks `session_id` for V2 and legacy rows; the `m10-06` E2E locks 6 rows, 12 links, their hrefs and focusability.
- The 08 design document records the step-4 click contract in both "seven-step presentation" and "interaction", so a future layout pass does not drop it again.

## Alternatives considered

- **Reuse the V2 prototype's global `BAD_CASES` fixture to look up the Session**: the prototype can look up a global fixture because its data lives in the page, while production data comes from the database; maintaining a mirror only for links would create a second source of truth. Rejected.
- **Look up the Session from the already-loaded step-3 potential rows**: step 3 is paged at 5 rows and may not be loaded, so rows beyond the page cannot be resolved; coupling the two steps' load order would also make step switching fragile. Rejected.
- **Add an API that resolves a deep link by `attributionId`**: an extra request for a field that can travel with the row, while the URL still has to be built in the front end. Rejected.
- **Fix only the report ID and leave the source bad case as blue text**: the two columns in one table would behave differently, and the issue's acceptance requires the source link as well. Rejected.
- **Make the whole row clickable or give it `role="link"`**: it would conflict with text selection and copying, and a native anchor is already focusable and can open a new window. Rejected.

## Consequences

- Both step-4 links share `badCaseDeepLink` with step 3 and the error list, so the deep-link format has one definition; the error page's `at` resolution is already covered by tests.
- The contract adds one required field; the database and attribution algorithms are unchanged, and old clients simply ignore the extra field.
- Legacy rows use the persisted `probe_session_id`; historical data without a Session does not get a fabricated link.
- The new component and E2E assertions turn red if either column falls back to plain text, `at` is dropped, or `target` / `rel` changes.
- If the error-detail route changes, `badCaseDeepLink` must change with it; this change did not copy URL assembly into the component.
