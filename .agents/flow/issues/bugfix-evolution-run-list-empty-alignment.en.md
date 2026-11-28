# Keep the evolution run list top-aligned at content height

English | [中文](bugfix-evolution-run-list-empty-alignment.md)

```yaml flow
kind: issue
id: bugfix-75
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - apps/web/src/pages/evolution/**
  - apps/web/src/styles/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-28-evolution-run-list-empty-alignment.md
github:
  number: 669
  url: https://github.com/Shadow-Azure/harness-evolution/issues/669
```

## Background

A user screenshot shows large vertical gaps between the page intro and "Running (0)", between group labels and their empty cards, and between the cards themselves when the workspace has no evolution runs at `/workspaces/<wid>/evolution`; the two empty cards are also much taller than a single-line hint needs. The screenshot was not measured on site, so reproduction uses computed styles and element bounds.

The list root `.run-list-page` uses `display: grid`, and `apps/web/src/styles/main.css` gives it `height: 100%` so it owns page-level scrolling inside the workspace shell. The grid container does not set vertical content alignment, so the default `align-content: normal` distributes free space across auto rows and stretches the intro, groups, and empty cards on an empty or sparse list. #496 covers multi-card scrolling and #415/#422 cover the low-content Session page; neither covers this case.

## Goals

- Keep the page intro, group labels, and empty hints top-aligned at content height on empty and sparse lists, with no gap growth as the viewport gets taller.
- Keep both group labels, zero counts, empty hints, and the launch entry.
- Keep adjacent gaps and empty-card height within 2 CSS px when only the viewport height grows at a fixed width.
- Keep long-list scrolling, mobile document scrolling, and the no-horizontal-overflow contract.

## Design authority

- [08 §8 Evolution list page](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L612): the intro, RunGroup, and RunCard structure and the contract that the list root owns page scrolling.
- [V2 prototype evolution list](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html): group labels, empty hints, and cards flow from the top in normal document flow instead of filling the remaining viewport.
- [#496](https://github.com/Shadow-Azure/harness-evolution/issues/496): keep the page-level and narrow-screen scrolling contract.

## Implementation

Inspect the page and group grid tracks, `align-content`, `min-height`, and empty-card styles, then remove the confirmed stretch while keeping `height: 100%` page scrolling: the list root aligns its grid content to the start at each row's content height; the empty card keeps its own padding and no longer stretches with the container. Reuse existing spacing tokens; do not hide groups or remove scrolling.

Add a browser regression with synthetic runs at 0/0, 0/1, 1/0, 1/1, and 3/5 across 1366×768, 1920×1080, and 390×844: assert top alignment, viewport-height-independent empty-card height and adjacent gaps, and keep the long-list scrolling coverage.

## Implementation steps

1. Reproduce with a synthetic workspace, collect element bounds and computed styles, and confirm the stretch source.
2. Add a browser regression that fails on the vertical stretch, then make the scoped style fix.
3. Compare same-viewport screenshots, re-run long-list scrolling, and add the design note and Agent Note.

## Dependencies and boundary

- No blocking dependency; relates to #496.
- Scope is the evolution list layout, its browser regression, and design notes; no API, contract, or run-data changes.

## Verification

```sh
pnpm test:e2e -- m5-run-list
pnpm typecheck:web
pnpm lint:web
pnpm verify:web-style
pnpm verify:flow
```

- The new regression fails before the fix and passes after; empty-card height and adjacent gaps differ by at most 2 CSS px between 1366×768 and 1366×1080.
- With 3/5 runs the long list still scrolls to the last card; at 390×844 the document scrolls with no horizontal overflow.
- Type, lint, style, and flow gates pass; the PR includes before/after screenshots at the same viewport and geometry measurements.

## Acceptance

- On an empty list the intro, both group labels, and empty hints flow from the top without a stretched band.
- At a fixed width, raising the height from 768 to 1080 changes adjacent gaps and empty-card height by at most 2 CSS px (same zoom, font, and copy).
- Empty cards keep sensible padding; the launch entry, zero counts, and hints stay visible and sparse lists stay compact.
- #496 long-list and mobile scrolling do not regress; the PR provides before/after screenshots and geometry measurements.

## Gates and CI

- The focused E2E runs in existing CI; frontend unit tests, types, lint, style, docs, and flow gates run with at least 80% coverage.

## Non-goals

- Do not change run logic, permissions, API, card fields, the global shell, or other pages.
- Do not hide empty groups or remove scrolling to mask the symptom.
