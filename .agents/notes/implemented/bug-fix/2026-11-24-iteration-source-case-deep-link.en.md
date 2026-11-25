# Agent Note: Wire step 5 and 6 source bad cases back to the error deep link

Status: implemented

English | [中文](2026-11-24-iteration-source-case-deep-link.md)

## Problem

The cluster source table in run-detail step 5 and the turn source table in step 6 share `StepCaseTable`. That component renders `<a>` only when it receives both `wid` and `caseSessions[badCaseId]`; otherwise it silently falls back to plain text. That is exactly why production's "source bad case" IDs were not clickable and not keyboard-focusable.

The mapping input was already available: run detail reads `steps/attribution` for its info panel, and `payload.rows[]` carries both `badCaseId` and `sessionId`. The page never folded those rows into a map the way `ClusterPreview.vue` does, `RunStepContent` never passed it down, and `StepIterations` did not even have a `caseSessions` prop or hand `wid` to the table. Only the cluster-only preview page could click the same table; steps 5 and 6 failed from the same root cause.

Tests did not lock the wiring: `StepContent.test.ts` mounted `StepCaseTable` directly or only asserted cluster highlighting, and no case mounted `RunDetail` to assert anchors in steps 5 and 6, so this regression stayed green.

## Decision

- `RunDetail.vue` derives `caseSessions: Record<string, string>` from the loaded `attributionData.payload.rows`, using the same shape as `ClusterPreview.vue`; page-level parallel reading of attribution is the established source, see `08 §11`.
- `RunStepContent.vue` gains a `caseSessions` prop and forwards it to `StepClusters` and `StepIterations`; `StepIterations.vue` gains the same prop and passes both `wid` and the map into `StepCaseTable`.
- `StepCaseTable.vue` adds `target="_blank"` and `rel="noopener noreferrer"` to the link branch, plus a full-ID `title`, an `aria-label` of "source problem …, opens the problem description in a new window", and a `:focus-visible` outline; styling aligns with the V2 prototype `.idlink` (monospace, blue, dashed underline, pointer, solid on hover). The deep link reuses `badCaseDeepLink()`, and the `?case=&tab=attr` rule is unchanged. Without a mapping it still degrades to plain text with the full `title` (dimmed to `--text-dim`), never rendering an empty `href`.
- Regression coverage is layered: `StepContent.test.ts` mounts steps 5 and 6 separately and asserts the anchor's Session, `case`, `tab=attr`, `target`, plus the no-mapping fallback; `RunDetail.test.ts` asserts the page wires the attribution map into both steps; the `m10-06` E2E asserts real DOM anchors using the existing fixture's expanded cluster and completed turn.
- `08 §10.3` gains one sentence stating that step-6 source bad case IDs deep-link to the error detail, matching the existing step-5 and `§11` descriptions.

## Alternatives considered

- **Add a Session field to the `steps/clusters` / `steps/iteration` contract**: rejected. `08 §11` already chose page-level `steps/attribution` mapping; adding a field widens the API and contract surface and forks the cluster-only page's existing implementation.
- **Let `StepCaseTable` fetch attribution itself**: rejected. It couples a presentational component to the network and query cache, repeats the request across the cluster-only page, step 5 and step 6, and erases the "plain text without a mapping" boundary.
- **Query the Session per row by `badCaseId`**: rejected. N source rows would mean N requests while the attribution response already carries every required field.
- **Only add CSS so the text looks clickable**: rejected. Without an anchor and `href` it still cannot open in a new window, receive keyboard focus, or carry a real deep link.
- **Also rewrite the step-5 `cb-label` copy**: out of scope here. Copy is a non-goal; restore the real link first and handle label/prototype alignment separately.

## Consequences

- Steps 5 and 6 render real deep links whenever the attribution step is readable; clicking opens that row's bad-case error detail in a new window, and cases from different Sessions land on their own Session without cross-wiring.
- The map depends on `steps/attribution` being loaded and that step being `clickable`. When attribution is unreachable or a case is absent from its rows, the table stays plain text with the full ID in `title`, never an empty anchor.
- No API, `packages/contracts`, clustering/iteration algorithm or deep-link tab rule changes; the cluster-only preview shares the same component, so its source IDs also open in a new window, matching the prototype.
- Component, page and E2E layers lock the wiring, so changing `StepCaseTable` props or the page pass-through chain again will fail first.
