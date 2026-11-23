# Evolution list page lacks a page-level scroll container, so run cards past the first screen are clipped

English | [中文](bugfix-evolution-list-scroll.md)

```yaml flow
kind: issue
id: bugfix-25
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - apps/web/**
  - tests/e2e/**
  - tests/support/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-22-evolution-list-page-scroll.md
github:
  number: 496
  url: https://github.com/Shadow-Azure/harness-evolution/issues/496
```

## 背景

On 2026-11-22 the production evolution list page (`/workspaces/<wid>/evolution`) could not scroll down at a 1408×788 CSS viewport. The scene had 3 running and 5 history run cards, the list content was 1348px tall, and the workspace shell's `main.workspace-main` exposed only 732px; `main` clipped the overflow with a fixed height and `overflow: hidden`, while the list root `.run-list-page` only declared `display: grid; gap: 14px` with no `height` or `overflow-y`, and the document itself did not scroll. The mouse wheel, PageDown, End, and `window.scrollTo` could not move the page, no scrollbar appeared at the window's right edge, and users had to change zoom or use a taller monitor.

Within the same shell, the overview page `.overview-page`, the workspace admin page `.admin-page`, and the run detail `.run-detail-page` all provide page-level scrolling with `height: 100%; overflow-y: auto`; only the evolution list (and the object configuration page, which also reuses `.evolution-page-frame`) did not. The V2 prototype scrolls through the document, so a longer list always grows the page. The full production measurements, screenshots, and root-cause analysis are in GitHub #496.

## 目标

- The evolution list scrolls vertically at 1366×768, 1408×788, 1440×900, 1500×837, and 1920×1080, and the wheel, PageDown, End, and scrollbar dragging can reach the last history card.
- The scrollbar sits at the window's right edge; the content column keeps the 1080px frame (1032px of content plus 24px inline padding) without horizontal shift or a second scrollbar.
- Only the list page's scroll ownership changes; run-card data, order, grouping, fields, buttons, and the launch wizard stay unchanged, as do the scroll implementations of other pages.
- A real-browser regression covers reachability and content-column placement with 3 running plus 5 history cards at constrained viewports.

## 设计依据

- [08 §8 Evolution list page](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L610-L633): the page contains a header, two RunGroups, and N RunCards, and the design does not limit the card count.
- [08 §5 Session browser page](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L482-L488): the workspace shell's document does not scroll, and each page's content area owns its scrolling.
- [08 §10 Run detail page](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L761-L765): the page root owns page-level scrolling with `height` + `overflow-y: auto`, which this issue reuses.
- [V2 prototype list rendering](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L5233-L5250): cards render directly into the content container, and the content height naturally grows the document.
- [#362 Overview scrollbar placement](https://github.com/Shadow-Azure/harness-evolution/issues/362) and [#423 Run-detail page scrolling](https://github.com/Shadow-Azure/harness-evolution/issues/423): the app already settled on page-level scrolling with the scrollbar at the window's right edge.

## 实现内容

- Add `.workspace-main .run-list-page` after the `.workspace-main .evolution-page-frame` rules in `apps/web/src/styles/main.css`: `height: 100%`, `width: 100%`, `overflow-y: auto`, inline padding `max(24px, calc((100% - 1080px) / 2 + 24px))`, and the existing 20px / 64px block padding. The full-width node paints the scrollbar at the window's right edge, and the symmetric padding preserves the 1080px frame and the 1032px content column.
- Add a ≤640px override: `height: auto`, `overflow-y: visible`, `padding: 8px 24px 0`, following `main.workspace-main`'s mobile document-scroll branch and avoiding nested scrollbars.
- Extend `tests/e2e/m5-run-list.test.mjs`: at 1408×788, 1366×768, and 1920×1080 assert that the list is the only scroll container, the document does not scroll, the scrollbar's right edge equals the window, and the content column's left edge and width match the 1080px frame, then reach the last card with a real wheel, PageDown, and End; at 390×844 assert document scrolling and no second scroll container on the list root.
- Update the scroll-ownership note in §8 of `plans/fullstack-design/08-frontend-implementation.md` and add an Agent Note recording the page-level scrolling and 1080px-frame trade-off.

## 实施步骤

1. Add the list page's page-level scroll rules and the ≤640px override in `apps/web/src/styles/main.css`.
2. Extend the scroll and content-column regression in `tests/e2e/m5-run-list.test.mjs`.
3. Update §8 of doc 08, add the Agent Note triple, and run `pnpm record:i18n`.
4. Run the focused E2E, `pnpm test:web`, `pnpm typecheck:web`, `pnpm lint:web`, `pnpm verify:web-style`, `pnpm verify:docs`, and `pnpm verify:flow`.
5. Capture same-scene, same-theme Before/After screenshots and measurements at 1408×788, and keep `(#496)` in the PR title.

## 依赖与交付边界

- Dependencies: no external resources and no API, contract, database, or authentication changes.
- Delivery surface: `apps/web/**`, `tests/e2e/**`, `tests/support/**`, `plans/**`, `.agents/**`.
- The evolution object configuration page still reuses `.evolution-page-frame` and has no page-level scroll container; this issue only targets `.run-list-page` and does not change that page, and unifying them needs a separate issue.
- Do not write production URLs, accounts, passwords, run data, or screenshots into the repository; Before/After evidence lives only in the PR description or release assets.

## 独立验证

```sh
pnpm test:e2e -- "m5-run-list"
pnpm test:web
pnpm typecheck:web
pnpm lint:web
pnpm verify:web-style
pnpm verify:docs
pnpm verify:flow
```

- At 1408×788 `.run-list-page` has `scrollHeight` greater than `clientHeight`; after three wheel gestures `scrollTop > 0`, and after End the difference between `scrollTop + clientHeight` and `scrollHeight` is ≤2px; `document.scrollingElement.scrollHeight === clientHeight`.
- The scroll container's right edge is within 2px of `window.innerWidth`; at 1408 the left padding is about 188px and the content column about 1017–1032px, while at 1920 the left padding is about 444px and the content column still about 1017–1032px.
- 1366×768 and 1920×1080 also reach the bottom; at 390×844 the `document` scrolls and the list root has `scrollHeight === clientHeight`.
- All commands above pass, and `verify:web-style` reports no new color tokens.

## 验收标准

- At 1408×788 the wheel, PageDown, End, and scrollbar dragging reach the last history card, and the vertical scrollbar sits at the window's right edge.
- The first screen's top layout stays unchanged: the content column's left edge, width, card gaps, and header position do not shift horizontally.
- 1366×768, 1440×900, 1500×837, and 1920×1080 reach the list bottom; below 640px no nested scrollbars appear.
- The new real-browser regression fails before the fix and passes after it; run data, API responses, card order, and launch-wizard behavior stay unchanged.
- The PR description contains 1408×788 Before/After screenshots and key measurements and links this issue; the Agent Note and the documentation gates pass.

## 门禁与 CI

- E2E: `pnpm test:e2e -- "m5-run-list"`, included in CI's `pnpm test:e2e`.
- Unit tests and coverage: `pnpm test:web` (coverage ≥80%).
- Types and lint: `pnpm typecheck:web`, `pnpm lint:web`, `pnpm verify:web-style`.
- Docs and flow: `pnpm verify:docs`, `pnpm verify:flow`; the PR title and commits carry `(#496)`.
- One reviewer inspects the change before merge; deliver for human review after CI is green, and a person merges this PR.

## 非目标

- No rework of the list's information architecture, card styles, grouping, filters, pagination, or infinite scrolling.
- No changes to the scroll implementations of the run detail, cluster-only, object configuration, overview, or workspace admin pages.
- No changes to `main.workspace-main`'s fixed shell, header height, or global `overflow`.
- No page-width change from 1080px to 1720px; page width and scrolling are separate problems.
- No hiding scrollbars, compressing card content, or requiring users to change zoom or monitors.
- No changes to production data, APIs, contracts, authentication, or deployment configuration.
