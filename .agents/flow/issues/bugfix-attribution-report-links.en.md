# Step 4 attribution report IDs link to the attribution analysis

English | [中文](bugfix-attribution-report-links.md)

```yaml flow
kind: issue
id: bugfix-06
milestone: bugfix
depends:
  - m21-01
priority: P2
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-20-attribution-report-link.md
github:
  number: 443
  url: https://github.com/Shadow-Azure/harness-evolution/issues/443
```

## Background

The production run detail renders the step-4 "attribution report ID" as plain text: the cell reports `cursor: auto`, the table contains zero anchors, and clicking the ID changes neither the URL nor the page. The V2 prototype (`plans/ui-prototype-v2/harness-evolution.html:5352-5353`) opens the bad case's error detail on the attribution-analysis tab from the same cell. Step 3 and the error detail page already share the bad-case deep-link convention. Production matches the current `main`, so this is neither a stale build nor a cache artifact.

The direct cause is `apps/web/src/pages/evolution/components/StepAttribution.vue`: both the report-ID and source-bad-case cells are plain `<td>` elements with no anchors, and the component never receives `wid`. On the data side, `StepAttributionRow` (`apps/api/app/service/evolution/stages.py`) exposes `bad_case_id` / `attribution_id` but no `session_id`, and the error-detail deep link requires the Session. Full production measurements and prototype comparison are in [#443](https://github.com/Shadow-Azure/harness-evolution/issues/443).

## Goals

- Render the step-4 attribution report ID as a link that opens the matching bad case's error detail in a new window on the "attribution analysis" tab, with `case` / `tab=attr` / `at` matching the row.
- Render the source bad case with the same convention on the "problem description" tab, removing text that looks like a link but is not clickable.
- Give both columns focusable anchors with `title` and `aria-label`, while preserving the existing statistics, cached/fresh chips, confidence values and table layout.
- Lock the link behaviour with component tests and E2E, and record the step-4 click contract in the design document.

## Design authority

- [08 §10.1 seven-step presentation](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L781): the step-4 columns are source bad case / attribution ID / category / symptom / result source / confidence.
- [V2 prototype `evStepAttr()`](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L5344-L5365): the source column uses `evCaseLink`, and the report ID uses `<a class="idlink">` pointing at `caseDeepLink(..., 'attr', ...)` with `target="_blank"` and `rel="noopener"`.
- [Existing deep-link helper](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/web/src/utils/badCaseId.ts): `badCaseDeepLink(wid, sessionId, badCaseId, tab, attributionId)` builds `/workspaces/:wid/sessions/:sid/errors?case=...&tab=...&at=...`.
- [Step-3 reference implementation](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/web/src/pages/evolution/components/StepPotential.vue#L96-L105): the source bad case is a new-window `badCaseDeepLink(..., 'desc')` link with `aria-label` and `rel="noopener noreferrer"`.

## Implementation

- Contract and API: add a required `session_id` to `StepAttributionRow`; V2 takes `candidate.session_id`, legacy takes `first.probe_session_id`; run `pnpm contract:generate` to refresh OpenAPI and generated types.
- `StepAttribution.vue`: add a `wid` prop and render both columns with `badCaseDeepLink`. The report ID uses `tab=attr` and `at=row.attributionId`; the source bad case uses `tab=desc`. Anchors use `target="_blank"` and `rel="noopener noreferrer"`, keep the full ID as visible text and `title`, and add `aria-label`.
- `RunStepContent.vue`: pass the existing `wid` down to `StepAttribution`.
- Tests: component tests assert `href`, `target`, `rel` and `aria-label` on both links; an API test asserts the step-4 row carries the correct `session_id`; the `m10-06` E2E asserts link count, href shape and focusability while keeping the existing statistics assertions.
- Documentation: add the click behaviour to the step-4 table description in `plans/fullstack-design/08-frontend-implementation.md`, and add an Agent Note explaining why the API supplies `sessionId` and why the prototype's global fixture lookup is not reused.

## Implementation steps

1. Change `StepAttributionRow` and both row builders, run `pnpm contract:generate`, and confirm the front-end and back-end types agree.
2. Change `StepAttribution.vue` and `RunStepContent.vue`, following the link style and accessibility pattern of `StepPotential.vue`.
3. Update the web component tests, the `RunDetail.test.ts` / `StepContent.test.ts` fixtures, the API stage test and the `m10-06` E2E.
4. Update the 08 design document and the bilingual Agent Note set.
5. Capture Before / After screenshots on a local production-shaped page with the synthetic fixture, compare against the prototype at the same viewport, and run the focused unit tests, typecheck, lint, E2E and flow/document gates.

## Dependencies and boundary

- Depends on m21-01 (the run detail already follows the V2 layout and the step-4 table shape is stable).
- Boundary: only the step-4 DTO, component, matching tests and documentation change; attribution, clustering, caching and evaluation algorithms, the step-3 and error-detail deep-link conventions, and the table layout stay as they are.
- Production screenshots and Session content are not committed to the repository; Before / After evidence lives in the PR description and local reports only.
- The bugfix milestone is closed after the reporter confirms the whole flow; this PR uses `Refs #443` and does not close the issue automatically.

## Verification

```sh
pnpm --filter @harness/web exec vitest run src/pages/evolution/components/RunDetailConformance.test.ts src/pages/evolution/components/StepContent.test.ts src/pages/evolution/RunDetail.test.ts
pnpm --filter @harness/web exec vitest run src/utils/badCaseId.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:api -- -k "m10_04_stages"
pnpm test:e2e -- "m10-06 run detail"
pnpm verify:flow
pnpm lint:docs
```

- Component tests: step 4 has anchors in both columns; the source link ends with `case=...&tab=desc`; the report link carries `tab=attr&at=<attributionId>`; both use `target="_blank"` and `rel="noopener noreferrer"`, and `aria-label` contains the full ID.
- API tests: the V2 and legacy step-4 rows both return a non-empty `session_id`, and the V2 value equals the candidate Session.
- E2E: `run-v2-completed` step 4 has 6 rows and 12 links; the report link's `case` / `session` / `at` match the fixture and the first report link is focusable; a new case navigates to the generated report/source hrefs and asserts the selected attribution on the analysis tab and the description tab.
- Production-shaped page at 1500×837: the report ID is a blue link with a hover title, reachable with Tab, and opens the attribution analysis in a new window.

## Acceptance

- On the production-shaped page, the step-4 attribution report ID is a link with a hover title and keyboard focus; clicking opens the matching bad case's error detail in a new window on the attribution-analysis tab.
- The source bad case opens the problem-description tab, and no text that looks like a link remains non-clickable.
- With multiple attributions, the URL's `at` matches the row's `attributionId`; the step-4 statistics, cached/fresh chips and confidence display are unchanged.
- Focused unit tests, `pnpm typecheck:web`, `pnpm lint:web`, the related E2E, `pnpm verify:flow` and the documentation gates pass.

## Gates and CI

- Runs `pnpm test:web` (component tests and coverage), `pnpm test:api` (step projection), `pnpm typecheck:web`, `pnpm lint:web`, `pnpm test:e2e` (m10-06), `pnpm contract:check`, `pnpm verify:flow`, and `pnpm lint:docs` / `verify:docs`.
- Contract artifacts come from `pnpm contract:generate` and are never hand-edited; the PR includes the OpenAPI and generated-type diff.

## Non-goals

- Do not change attribution, clustering, caching or evaluation algorithms, and do not change the existing deep-link conventions of step 3 or the error detail page.
- Do not rearrange the step-4 table, column order, statistic definitions or style tokens.
- Do not commit production screenshots or Session content; evidence stays in the issue / Release / PR description.
- Do not fabricate links for historical rows without a Session; legacy rows use only the real `probe_session_id`.
