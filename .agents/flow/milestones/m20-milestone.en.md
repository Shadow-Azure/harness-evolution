# M20 Launch-wizard Session association display fix

English | [中文](m20-milestone.md)

```yaml flow
kind: milestone
id: m20
title: M20 启动向导 Session 关联展示修复
status: planned
github:
  number: 28
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/28
```

## Goals

Make step 2, "Session association", of "Start self-evolution" show all four columns together at a 1440-wide viewport: the Session cell shows a short label with a single-line ellipsis and a full-title tooltip while keeping the short Session ID, and a long prompt no longer widens the table or pushes the association evidence columns out of the modal.

## Scope

The short-title field of the `SessionPreviewItem` preview response, the Session cell and table horizontal layout in `LaunchWizard.vue`, generated shared contracts, API and component tests, the m10-05 browser E2E, design docs, and the Agent Note.

## Acceptance

- At a 1440-wide viewport and the 720-wide modal, `Session`, "object appears", "object trigger time", and "bad case count" are visible together, and a long title produces no horizontal scroll.
- The Session cell shows a short label and exposes the full title through `title`; the short Session ID stays.
- The preview response returns `short` (from `session_families.short_title`) plus the full `title`.
- Session association, bad case statistics, paging, and ordering are unchanged; component and E2E tests cover the long-title regression.
- The PR description carries before/after captures from the real application and a comparison with the same V2 prototype region.

## Non-goals

No change to `short_title` generation, Session association, or statistics; no alignment of condition chips, statistic-row item count, or full UUID display; no production Session content committed to the repository.
