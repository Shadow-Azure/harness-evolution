# Target config page fixes its content column at 1080px, clipping the 8-column table

English | [中文](bugfix-target-config-page-width.md)

```yaml flow
kind: issue
id: bugfix-24
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - apps/web/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 498
  url: https://github.com/Shadow-Azure/harness-evolution/issues/498
```

## Background

At a 1408×788 CSS viewport, the production 「Evolution → Target config」 page (`/workspaces/<wid>/evolution/targets`) renders an 8-column table about 1071px wide, but `.workspace-main .evolution-page-frame` caps the content column at 1080px, leaving the table scroller a 996px `clientWidth`. The rightmost 「Actions」 column is clipped by the horizontal scroller. At 1920px the content column is still 1080px, wasting 420px on each side. Measurements, prototype comparison and the in-browser candidate fix are recorded in GitHub #498.

## Goals

- Render the target config page inside the V2 prototype's 1720px content container: at 1408px the content panel is 1360px, all 8 columns are visible, and the table has no horizontal scrollbar.
- Cap and center the content column at 1720px at 1920px, so the available page width is used.
- Keep the table's own horizontal scrolling as a fallback at 1024px and below; do not change columns, fields, sorting, actions or data semantics.

## Design authority

- [08 §9.5 Target config page](../../../plans/fullstack-design/08-frontend-implementation.md): the page follows V2 with 8 columns (object type, object name, repository, subdirectory, baseline, test projects, state, actions), wider than the prototype's 6 columns.
- [V2 prototype `.evo-app .wrap`](../../../plans/ui-prototype-v2/harness-evolution.html#L606): `width: min(100%, calc(1720px / var(--ui-zoom, 1)))`, `max-width: none`, `padding: 20px 24px 64px`; the content panel is 1360px at 1408px.
- [V2 prototype target panel](../../../plans/ui-prototype-v2/harness-evolution.html#L5684): the table fills the `.wrap` width and needs no horizontal scrolling.

## Implementation

- `apps/web/src/styles/main.css`: the shared width becomes `min(var(--evolution-page-max-width, 1080px), 100%)`, and `.target-config-page` sets `--evolution-page-max-width: 1720px`. The 1080px default still applies to the evolution list and workspace admin pages, and the ≤640px `width: 100%` branch stays effective.
- `tests/e2e/m5-target-config.test.mjs`: at 1408px assert page width 1408, content width 1360, table `scrollWidth === clientWidth`, and fully visible actions; add a 1920px assertion for page width 1720, content width 1672 and no table overflow; keep the 1024px horizontal-scroll fallback.
- `tests/e2e/m5-run-list.test.mjs` and `tests/e2e/m7-09-workspace-admin.test.mjs`: continue to assert that the evolution list and workspace admin pages keep 1080px.
- Add an Agent Note recording the decision to widen one page to 1720px while other pages keep 1080px, and that boundary.

## Implementation steps

1. Update the E2E assertions first and reproduce the table overflow on the 1080px baseline.
2. Add the 1720px page-width rule for the target config page in the shared stylesheet.
3. Start the app locally and compare 1408×788, 1920×1080 and 1024×768 against the V2 prototype and Before/After screenshots.
4. Run the focused E2E, typecheck, lint and flow gates; attach Before/After evidence to the PR.

## Dependencies and boundary

- Dependencies: none.
- Boundary: change only the target config page width and its regression test; do not unify the 1080px width of the evolution list and workspace admin pages.

## Verification

```sh
pnpm test:e2e -- "m5 target configuration"
pnpm test:e2e -- "m5 run list"
pnpm test:e2e -- "m7-09 workspace-admin"
pnpm typecheck:web
pnpm lint:web
pnpm verify:flow
pnpm test:gates
```

- 1408×788: `.target-config-page` is 1408px wide with 1360px content; `.target-table` has `scrollWidth === clientWidth` and 「Edit / Disable / Delete」 are fully visible.
- 1920×1080: `.target-config-page` is 1720px wide and centered with 1672px content; the table does not overflow.
- 1024×768: the table keeps horizontal scrolling while the page itself has no horizontal overflow.
- All commands above pass.

## Acceptance

- At 1408×788 the content column grows from 1080px to 1408px and the content panel is 1360px, matching the V2 prototype at the same viewport; all 8 columns are visible, the actions column is not clipped, and the table has no horizontal scrollbar.
- At 1920×1080 the page width is capped at 1720px and centered; at 1024px and below the table scrolls horizontally and the page has no horizontal overflow.
- The page width and layout of the evolution list and workspace admin pages are unchanged, covered by the run-list and m7-09 width assertions.
- Before/After screenshots share the scenario, viewport, theme and data; Before is labelled with the baseline commit.
- All verification commands pass.

## Gates and CI

- `pnpm test:e2e -- "m5 target configuration"`, `pnpm typecheck:web`, `pnpm lint:web`.
- `pnpm verify:flow`, `pnpm test:gates`.
- CI must be green before human review; a person merges this PR.

## Non-goals

- Do not change table columns, fields, action buttons, sorting, data semantics or APIs.
- Do not unify the evolution list and workspace admin pages to 1720px.
- Do not change the V2 prototype, design tokens or other page layouts.
- Do not commit production screenshots, Session content or credentials.
