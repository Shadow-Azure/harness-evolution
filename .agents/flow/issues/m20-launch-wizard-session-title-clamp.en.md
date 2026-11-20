# Launch wizard step 2 shows short Session titles and keeps the table inside the modal

English | [中文](m20-launch-wizard-session-title-clamp.md)

```yaml flow
kind: issue
id: m20-01
milestone: m20
depends:
  - m10-05
priority: P2
status: done
scope:
  - apps/web/src/pages/evolution/**
  - apps/api/app/service/evolution/**
  - apps/api/app/db/crud/potential.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - .agents/notes/**
  - .agents/flow/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 404
  url: https://github.com/Shadow-Azure/harness-evolution/issues/404
```

## Background

The production "Start self-evolution" step 2, "Session association", renders the first prompt of each Session as the table title. A long prompt widens the table and pushes "object appears", "object trigger time", and "bad case count" out of the modal. The V2 prototype at the same place uses a short session name plus the Session ID, so all four columns fit. See [issue #402](https://github.com/Shadow-Azure/harness-evolution/issues/402) for the product report and the production/prototype evidence.

There are two causes: the preview contract `SessionPreviewItem` only returns `title`, so the frontend cannot use the `short` value the Session list already uses; and `table.rep` combines `white-space: nowrap` with no width bound, so the long title participates in table sizing. The fix adds the short-title data path and a presentation bound, without changing association, pagination, or statistics.

## Goals

- Show a readable short label in the step 2 Session cell with a single-line ellipsis, and expose the full title through the `title` tooltip.
- Keep the short Session ID; do not change the existing head/tail abbreviation.
- At a 1440-wide viewport and the 720-wide modal, keep `Session`, "object appears", "object trigger time", and "bad case count" visible together, with no horizontal scroll or hidden column caused by a long prompt.
- Return `short` from the preview API, sourced from `session_families.short_title`; keep `title` as the full title for the tooltip.
- Leave Session association, bad case counts, paging, and ordering unchanged.

## Design authority

- [05 §4.20 Self-evolution preview and launch](../../../plans/fullstack-design/05-api-design.md#420-自进化预览与启动v2): the `preview/sessions` response fields and paging contract.
- [08 §9.2 Four-step form and previews](../../../plans/fullstack-design/08-frontend-implementation.md#92-四步表单与预览): the step 2 columns and the Session title presentation.
- [V2 prototype](../../../plans/ui-prototype-v2/harness-evolution.html): the step 2 row uses `a.sess.short` with the full `a.sid`, and `.cell-sub` has a max width and ellipsis.

## Implementation

- `apps/api/app/service/evolution/potential.py`: add `short` to `AssociatedSession` and `SessionPreviewItem`, taken from `SessionRecord.short_title`; association logic is unchanged.
- `packages/contracts`: update `openapi.json` and the generated TypeScript types with `pnpm contract:generate`; do not hand-edit them.
- `apps/web/src/pages/evolution/components/LaunchWizard.vue`: render `item.short || item.title` with a `title` attribute carrying the full title; use a fixed-layout session table with a bounded title column and a single-line ellipsis; keep empty state and other columns' semantics.
- Tests: assert `short` in the API preview test; cover the clamped title and full tooltip in a component test; assert all four headers are inside the modal and the table has no horizontal overflow in E2E.
- Docs: record the `short` field and truncation contract in design docs 05/08, and add an Agent Note for the "short-title data path plus presentation clamp" decision.

## Implementation steps

1. Extend the preview DTO and association result, with API unit tests.
2. Run `pnpm contract:generate` and commit the contract change.
3. Adjust the Session cell and table layout in `LaunchWizard.vue`, with a component test.
4. Add a long-prompt title to the m10-05 E2E seed and assert four visible columns with no horizontal overflow.
5. Update the design docs, Agent Note, and flow issue; run gates and a real-browser smoke.

## Dependencies and boundary

- Depends on: m10-05
- Boundary: only the step 2 Session cell and the table's horizontal layout; the condition chips, statistic row, Session ID format, trigger column, and paging behavior stay as they are.

## Verification

```sh
pnpm contract:check
apps/api/.venv/bin/python -m pytest apps/api/tests/m10-02-potential-matcher/test_preview_api.py apps/api/tests/test_openapi.py
pnpm test:web -- LaunchWizard
pnpm lint:web && pnpm typecheck:web
pnpm test:e2e -- --pattern m10-05
pnpm test:gates && pnpm verify:docs && pnpm verify:flow
```

- The preview response contains `short`, equal to `session_families.short_title`.
- With a long title, all four headers are inside the modal and the table's `scrollWidth` does not exceed the container's `clientWidth`.
- The title shows an ellipsis and its hover text equals the full `title`.

## Acceptance

- At a 1440-wide viewport, step 2 with a long-prompt Session keeps the four columns visible and does not widen the table.
- The short label, full-title tooltip, and short Session ID are all present.
- Associated Session counts, paging, ordering, skipped counts, and version-unknown counts are unchanged.
- Component and E2E tests cover the long-title regression.

## Gates and CI

- Hits `pnpm contract:check`, `pnpm lint:web`, `pnpm typecheck:web`, `pnpm test:web`, `pnpm test:api`, `pnpm test:e2e`, `pnpm test:gates`, `pnpm verify:docs`, and `pnpm verify:flow`.
- The PR and commit titles reference this issue, and the PR description references product issue #402.

## Non-goals

- Do not change how `session_families.short_title` is generated, nor Session association, bad case statistics, or paging.
- Do not align the condition chips, statistic row item count, or full UUID display; those differences stay recorded in the product issue.
- Do not commit production Session content or screenshots into the repository.
