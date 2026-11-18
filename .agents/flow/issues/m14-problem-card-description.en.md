# Session problem cards show the description and evidence per the prototype

English | [中文](m14-problem-card-description.md)

```yaml flow
kind: issue
id: m14-01
milestone: m14
depends: []
priority: P1
status: in-progress
scope:
  - apps/web/**
  - tests/e2e/**
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr:
  - ../../notes/implemented/feature/2026-11-18-problem-card-description.md
github:
  number: 371
  url: https://github.com/Shadow-Azure/harness-evolution/issues/371
```

## Background

[#370](https://github.com/Shadow-Azure/harness-evolution/issues/370) records that the production Session error page (`/workspaces/{wid}/sessions/{sid}`) renders the attribution summary as the second line of each problem card in the bottom-right "问题" list. Unanalyzed cases always say "尚未完成归因分析", and the type badge, full case ID, and "关联：…" row are missing. The V2 prototype `FindingList` leads with the problem description and shows the `self` / `discovery` type badge, object badge, full case ID, facts, "关联：…", and "定位 ↗".

The non-compact `BadCaseList` template used `badCaseSummary(problem)` as the body. That helper returns a fixed string for `unanalyzed` and the attribution `summary` / `reason` for analyzed cases, so the card never shows the `reason` description. The ID is truncated to eight characters, and `badCaseSummary` has no other consumer.

## Decision

The prototype defines the problem-card hierarchy: the second line shows `problem.reason` (the description), the attribution state stays a lightweight chip, and the card gains the type badge, object badge, full case ID, and "关联：…" row. The attribution summary no longer appears in the list. The prototype's `FindingList` leads with the description, and #370's goal is to let unanalyzed cases read the symptom from the session page without opening the error detail page.

## Goals

- Both unanalyzed and analyzed cases show the `reason` description in the session problem card, rendered safely as Markdown.
- The card gains the `badCaseType` (`self` / `discovery`) badge, the `objectName` badge, the full `badCaseId` (deep link kept), and the "关联：`objectType` · `objectName`" row.
- The attribution state stays a lightweight chip; the `degraded` marker stays visible.
- The whole card still locates the case in the execution flow, and links inside the description stay clickable.
- The V2 prototype `FindingList` mirrors the production implementation: the description follows the same Markdown contract.

## Design authority

- [V2 prototype Session BAD CASE list](../../../plans/ui-prototype-v2/harness-evolution.html): `FindingList` renders the BC number, title, type/object, full case ID, problem description, facts, association, and `定位 ↗`.
- [V2 prototype FindingDescription](../../../plans/ui-prototype-v2/harness-evolution.html): unanalyzed cases still render the description and only add "尚未归因" in the header; the description is rendered as Markdown.
- [08 §3.4 problem-list linkage / §5 Session overview](../../../plans/fullstack-design/08-frontend-implementation.md): the card hierarchy, whole-card locate, and Markdown contract.
- [05 §9 bad case DTO](../../../plans/fullstack-design/05-api-design.md) and [06 §4.1 bad_cases](../../../plans/fullstack-design/06-database-design.md): `reason` is the description body and `badCaseType` maps from `bad_case_type`.
- [2026-10-29 bad case title Agent Note](../../notes/implemented/feature/2026-10-29-bad-case-title.en.md): the error detail page renders a short title plus description, and the list card's main text is `title`.

## Implementation

- Rework the non-compact `apps/web/src/components/bad-cases/BadCaseList.vue` template into a "BC number + card body + locate" layout: the header renders the title, `type-badge`, `object-badge`, full `problem-id` deep link, state chip, and `degraded` marker in order; the body renders `renderMarkdown(problem.reason, { images: false })` with compact `.problem-detail.markdown` typography; facts become split key/value chips as in the prototype and the error detail page, followed by "关联：objectType · objectName"; "定位 ↗" closes the row.
- Reuse the compact template's overlay-button pattern for the card interaction: the body keeps `pointer-events: none`, links rise above the button, the existing single-selection semantics and `aria-pressed` stay unchanged, and Markdown links in the description do not trigger selection.
- Remove `badCaseSummary` from `badCaseDisplay.ts`, since nothing consumes it; `badCaseFacts` / `badCaseFactEntries` / `badCaseState` are unchanged.
- Type badges keep the error detail page's token mapping (`self` purple, `discovery` blue) so pages stay consistent; the prototype's stylesheet swaps them, which is a prototype internal inconsistency this change does not spread.
- Switch the V2 prototype `FindingList` `fi-detail` to the existing `renderMarkdown` and add `.fi-detail.markdown` paragraph/list/inline-code/code-block styles, matching production.
- Unit tests cover the BC number, type/object badges, full ID and aria, description body, Markdown lists and inline code, link attributes, raw-HTML escaping, image downgrade, facts, and the association row; E2E asserts card body, badges, full ID, association row, and F2P/P2P lists for all four fixture sessions.

## Implementation steps

1. Add failing `BadCaseList.test.ts` cases first: unanalyzed card shows the description, full ID, type/object badges, and association row; Markdown lists and inline code render as expected.
2. Rework the non-compact template and styles, wire `renderMarkdown`, and delete `badCaseSummary`.
3. Update the `m4-problem-cards` E2E to read text from the card instead of the button, and assert card content for all four fixture sessions.
4. Sync `08 §3.4` and the V2 prototype `FindingList`, and add an Agent Note recording "prototype wins", "why the summary goes away", and the overlay-button/link trade-off.
5. Re-capture before/after at the same 1440px viewport and the same fixture scenario, compare against the prototype screenshot, and fix any drift.

## Dependencies and boundary

- Dependencies: none new; the Markdown renderer from #363 (`utils/markdown.ts`) is merged, and the `BadCase` contract already has `badCaseType`, `reason`, `objectName`, `objectType`, and `metaData`.
- Boundary: only the Session problem card, its tests, the prototype, `08`, the Note, and evidence. The error detail page, API, data model, attribution logic, and other pages stay unchanged.
- No production Session or description content enters repository fixtures; evidence screenshots only travel with the PR.

## Verification

```sh
pnpm --filter @harness/web test -- src/components/bad-cases/BadCaseList.test.ts src/components/bad-cases/badCaseDisplay.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "m4 problem cards"
pnpm lint:docs
```

- Expected: unit tests cover the card body, full ID, badges, association row, and safe Markdown rendering for unanalyzed and analyzed cases; E2E asserts the session card shows the description (including the F2P/P2P lists) without regressing the error detail page; doc gates pass.
- Manual check: at 1440px, open the session problem list and confirm the description, badges, full ID, association, and locate affordance, then compare with the prototype screenshot.

## Acceptance

- An unanalyzed session card shows the problem description with the BC number, type/object badges, full case ID, association row, and "定位 ↗".
- The attribution summary of an analyzed case does not override the description; the state chip and `degraded` marker remain.
- The description renders as safe Markdown: raw HTML produces no nodes, external links are hardened, images downgrade, and plain text does not regress.
- The error detail page keeps the #363 description behavior.
- The V2 prototype `FindingList` mirrors production, and the PR carries refreshed before/after screenshots.

## Gates and CI

- `pnpm --filter @harness/web test -- src/components/bad-cases/BadCaseList.test.ts src/components/bad-cases/badCaseDisplay.test.ts`
- `pnpm typecheck:web`, `pnpm lint:web`, `pnpm test:e2e -- "m4 problem cards"`
- `pnpm verify:flow`, `pnpm test:gates`, `pnpm lint:docs`
- Commit messages and the PR title include `(#371)`; review follows `docs/review.md`.

## Non-goals

- No rework of the problem list information architecture, no change to the attribution state machine, data model, or API.
- No change to the error detail page's description or attribution display, and none to the execution-flow problem cards.
- No new Markdown library and no change to the `renderMarkdown` security configuration.
- No color or spacing changes on other pages.
