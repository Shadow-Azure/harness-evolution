# Run detail step 6 source bad case IDs are not clickable

English | [中文](bugfix-iteration-source-case-link.md)

```yaml flow
kind: issue
id: bugfix-45
milestone: bugfix
depends:
  - m21-01
priority: P2
status: ready
scope:
  - apps/web/**
  - tests/e2e/**
  - plans/fullstack-design/**
  - .agents/**
adr: []
github:
  number: 569
  url: https://github.com/Shadow-Azure/harness-evolution/issues/569
```

## Background

### Scenario

On 2026-11-24, in the production "Evolution → run detail" step 6 "Iteration", the user expanded turn #1 (12 source bad cases). Every red-boxed bad case ID is plain text: `swe-12a7bc0ee36f3dc94a22`, `swe-1444a4e1d1e064e1570a`, `swe-1969b8b81bb2e989e027`, and so on. The IDs are plain text: hovering shows neither a pointer nor an underline, and clicking changes neither the URL nor the page. The user expects the V2 prototype behaviour: the ID opens that bad case's error detail.

Production capture (red box marks the non-clickable area):

![Production step 6: source bad case IDs are plain text](https://github.com/Shadow-Azure/harness-evolution/releases/download/iteration-source-case-link-evidence-20261124/prod-step6-iteration-badcase-ids.jpg)

Path: production "Evolution" → history → a run that reached step 6 → run detail → step 6 "Iteration" → expand any turn → click an ID in the first column of "Source bad cases". Step 5 "Attribution clusters and severity" reuses the same table component and is equally non-clickable.

### Observations

- Turn 1 shows "Source bad cases (12 · grouped from attribution conclusions)"; all 12 IDs are text nodes and the table contains zero anchors.
- The ID cell has no anchor, `cursor: auto` and `tabIndex` `-1`, and cannot be focused by keyboard.
- Step 5's cluster case table has no anchors either; only the "cluster-only" preview page (`ClusterPreview.vue`) renders the same table with links.

### V2 prototype comparison

In `plans/ui-prototype-v2/harness-evolution.html#L5453-L5461`, `evCaseTable()` renders the first column through `evCaseLink()`; `evCaseLink()` (`#L5187-L5189`) emits `<a class="idlink" target="_blank" rel="noopener">` to the error detail. `.idlink` (`#L543`) sets `cursor: pointer` and a blue dashed underline. The step 5 cluster label explicitly says "Source bad cases (N · click an ID to open the error detail)" (`#L5577`); step 6's turn card reuses `evCaseTable` (`#L5546`), so the prototype's step 6 IDs are clickable too.

The same position in the V2 prototype (the shared step 5/6 source-case table, 1500×950 viewport, local demo run `EV-20261106-02`):

![V2 prototype: source bad case IDs are links](https://github.com/Shadow-Azure/harness-evolution/releases/download/iteration-source-case-link-evidence-20261124/proto-step6.png)

Prototype step 5 hint and link styling (same component):

![V2 prototype step 5: click an ID to open the error detail](https://github.com/Shadow-Azure/harness-evolution/releases/download/iteration-source-case-link-evidence-20261124/proto-step5.png)

The prototype demo run differs from production; the comparison is about the same page position, table and interaction.

### Root cause

Conclusion: **the run detail page never wires the `badCaseId → sessionId` map from the step 4 attribution rows into the shared `StepCaseTable`. The link branch can never resolve a Session and silently degrades to plain text; steps 5 and 6 share the cause.**

1. `StepCaseTable` renders `<a>` only when both `wid` and `caseSessions[badCaseId]` exist; otherwise it falls back to the `v-else` text branch (`apps/web/src/pages/evolution/components/StepCaseTable.vue#L26-L32`, `#L57-L68`). The text branch has no anchor semantics, so clicking does nothing.
2. Step 6 never passes the map: `StepIterations.vue#L213` renders `<StepCaseTable :cases="round.cases" />`, the component props (`#L10-L14`) have no `caseSessions`, and `RunStepContent.vue#L75-L80` does not pass it. Step 5's `StepClusters.vue` declares and forwards `caseSessions` (`#L13`, `#L191-L194`), but `RunStepContent.vue#L68-L74` on the run detail page passes no value, so it is empty too.
3. The run detail page already has the source data: `RunDetail.vue` loads `steps/attribution` when `attributionStep.clickable` (`#L199-L205`), but never folds `payload.rows` into `badCaseId → sessionId` like `ClusterPreview.vue#L70-L76`, nor passes it down (`RunDetail.vue#L956-L967`). `ClusterPreview.vue#L330` passes `:case-sessions`, so only the cluster-only preview links work; the run detail page misses that wiring.
4. The contract does not need a new field: production `steps/iteration` returns 12 source items with only `badCaseId/title/objectName/badCaseType/triggerAt/createdAt` and no Session; `plans/fullstack-design/08-frontend-implementation.md#L870` already chose to derive the map from `steps/attribution` in the page and not add a session field to the clusters contract. The missing piece is the page wiring, not the API.
5. Tests do not cover the wiring: `StepContent.test.ts#L482` mounts `StepCaseTable` directly, and the `StepClusters` cases only assert highlight and empty state; no test mounts `RunStepContent`/`RunDetail` and asserts anchors for step 5 or 6, so the regression stays green.

Impact: the only drill-down from step 6 (and from the shared step 5 table) is dead, so users cannot return to the source bad case's error detail to verify the scene, even though the table header says the cases were grouped from attribution conclusions.

## Goals

- Step 6 source bad case IDs become links that open that row's error detail in a new window, with the matching Session and case.
- Step 5's cluster case table gets the same wiring, so one root cause is not half-fixed.
- Links keep the existing `StepCaseTable` deep-link rule (`?case=<id>&tab=attr`) and do not add a second navigation convention.
- Component tests lock "steps 5 and 6 both render anchors with the right Session"; no API or contract change.

## Design authority

- [08 §10.3 Step 6 iteration card](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L834): expanded content order is source cases → patch → candidate → push → eval → final commit.
- [08 §10 step 5](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L808): the cluster source-case table's IDs deep-link to the error detail.
- [08 §11 cluster deep-link data source](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L870): the page derives `badCaseId → sessionId` from `steps/attribution`; no session field is added to the contract.
- [V2 prototype `evCaseLink`](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L5187-L5189) and [`evCaseTable`](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L5453-L5461): the first column is `<a class="idlink" target="_blank">`.
- [m21-01 run-detail alignment](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/flow/issues/m21-run-detail-prototype-alignment.md): steps 5 and 6 follow the prototype structure; this issue only adds the link wiring.

## Implementation

- `RunDetail.vue`: derive `caseSessions: Record<string, string>` (`badCaseId → sessionId`) from the loaded `attributionData.payload.rows` and pass it to `RunStepContent`, mirroring `ClusterPreview.vue#L70-L76`.
- `RunStepContent.vue`: add a `caseSessions` prop and forward it to `StepClusters` and `StepIterations`.
- `StepIterations.vue`: add a `caseSessions` prop and pass `:case-sessions="caseSessions"` to `StepCaseTable`.
- `StepCaseTable.vue`: add `target="_blank"` and `rel="noopener noreferrer"` to the link branch, matching `StepPotential`, `StepAttribution` and the prototype; keep `caseLink()`'s `?case=&tab=attr`. Without a map it still degrades to text (keeping `title`).
- Tests: add a `StepIterations` mount case in `StepContent.test.ts` asserting each `td.id a` has the row Session, `case`, `tab=attr` and `target="_blank"`; assert in the `RunDetail` tests that steps 5 and 6 both receive the map. If the `m10-06` E2E fixture has a completed turn, add a step 6 anchor assertion.
- Docs: add one sentence to 08 §10.3 that source bad case IDs deep-link to the error detail, so the next implementation does not render them as plain text.

## Steps

1. Derive and pass the map in `RunDetail.vue`, then through `RunStepContent.vue`/`StepIterations.vue`; run the existing `StepCaseTable` tests first to confirm component behaviour is unchanged.
2. Add `target`/`rel` in `StepCaseTable.vue` and confirm the cluster-only preview links do not regress.
3. Add `StepContent.test.ts` and `RunDetail` wiring tests; add the step 6 E2E assertion if the fixture supports it.
4. Update the 08 design sentence.
5. Capture same-viewport before/after screenshots against the V2 prototype (current production/main vs wired), and run focused tests, typecheck and lint.

## Dependencies and boundary

- Depends on: m21-01 (steps 5 and 6 already follow the V2 prototype and the table structure is stable).
- Boundary: only the run-detail presentation wiring, `StepCaseTable` link attributes, the related component/E2E tests and one 08 sentence; no API, `packages/contracts`, `StepClusterCase`, clustering/iteration algorithm or deep-link tab change.
- Production run IDs, Session content and screenshots stay out of the repository; evidence goes to the issue/Release only.

## Verification

```sh
pnpm --filter @harness/web exec vitest run src/pages/evolution/components/StepContent.test.ts src/pages/evolution/RunDetail.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "m10-06"
pnpm verify:flow
```

- Component tests: every step 6 source row has `td.id a` with the row's Session, `case=` and `tab=attr`, and `target="_blank"`; step 5 too; no anchor is rendered without a map.
- Production-like page at 1500×950: all 12 step 6 turn 1 IDs are links and open the matching error detail in a new window; step 5 too.
- Statistics, turn state, badges and table layout do not regress.

## Acceptance

- Step 6 source bad case IDs are clickable links with pointer/underline on hover and keyboard focus; clicking opens the row's error detail in a new window.
- Cases from different Sessions in the same turn resolve to their own Sessions, with no 404 or cross-linking.
- Step 5's cluster source table gets the same wiring and links.
- Without reachable attribution data the IDs degrade to text, with no empty `href`.
- Component tests, `pnpm typecheck:web`, `pnpm lint:web`, the related E2E and `pnpm verify:flow` pass.
- The reporter confirms final acceptance.

## Gates and CI

- `pnpm test:web` (component and coverage), `pnpm typecheck:web`, `pnpm lint:web`, `pnpm test:e2e` (m10-06 if added), `pnpm verify:flow`.
- Commit and PR titles carry `(#<this issue number>)`; the PR description carries before/after and V2 prototype comparison captures.
- A human reviews and merges after CI is green.

## Non-goals

- Do not change the `steps/clusters` / `steps/iteration` contracts or add a Session field to `StepClusterCase`.
- Do not change the deep-link tab convention (keep `StepCaseTable`'s `tab=attr`).
- Do not touch table columns, summary copy, clustering/severity/turn state or steps 1–4/7.
- Do not commit production run IDs, Session content or screenshots to the repository.
