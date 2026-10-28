# Restore prototype top nav: two entries and Session active state

English | [中文](m6-topnav-prototype-ia.md)

```yaml flow
kind: issue
id: m6-06
milestone: m6
depends: []
priority: P1
status: done
scope:
  - apps/web/**
  - tests/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 147
  url: https://github.com/Shadow-Azure/harness-evolution/issues/147
```

## Background

The interactive prototype's top navigation has exactly two entries (Session 错误查看, 自进化); error detail is a sub-page inside the Session view reached via in-page buttons, and the [merge report](../../../plans/14-15-ui-prototype/merge-completion-report.md) records the follow-up adjustment that hid the inner sub-tab bar entirely, leaving a single-level nav. The implementation, however, has three top-level entries: m1-09 scaffolding introduced the Sessions/Errors/Evolution trio plus a `/errors` placeholder route (its own test said "top-level errors entry arrives later"), and m2-09 aligned the prototype's visual system only, cementing "Sessions/Errors/Evolution underline navigation" into acceptance. The result: the top-level Errors entry is a dead end — `/errors` renders only a "please select a session" empty state, with no cross-session error-list API behind it and no action leading back to Sessions. Additionally, no nav item is active on `/sessions/:sid` or `/sessions/:sid/errors` (vue-router's `router-link-active` matches route records, not path prefixes, and these are flat sibling records), which contradicts the prototype where the Session tab stays active across sub-pages.

## Goals

- Restore the prototype information architecture in the top bar: two entries (Session 错误查看, 自进化) with Chinese labels, sub-captions, and the ID cross-link note on the right.
- Error detail's only entry returns to the Session view: `/errors` is retired into a redirect to `/sessions`.
- The Session entry stays active (blue underline) on `/sessions`, `/sessions/:sid`, and `/sessions/:sid/errors`; the Evolution entry stays active (purple) on `/evolution/**`.

## Design authority

- [02-features.md](../../../plans/fullstack-design/02-features.md): F1 "top nav: switching between the two views" and F2 "ID system: deep link into the session error detail with a tab" — only two top-level views exist, and error-detail deep links hang under Session.
- [03-frontend-architecture.md](../../../plans/fullstack-design/03-frontend-architecture.md): the route table registers only `/sessions/:sid/errors`; a top-level `/errors` does not exist.
- [Prototype](../../../plans/14-15-ui-prototype/harness-evolution.html) and [merge report](../../../plans/14-15-ui-prototype/merge-completion-report.md): the final shape — two nav entries, sub-captions, the right-side ID note, and hidden sub-tabs.

## Implementation

- `TopNav.vue`: remove the Errors entry; switch the two entries to the prototype's Chinese labels with sub-captions (Session 错误查看/会话轨迹与归因, 自进化/报告驱动的迭代优化); compute the active state from the path prefix (`/sessions*` → blue, `/evolution*` → purple) instead of `router-link-active`; add the ID cross-link note on the right; hide sub-captions and the note below 1100px (same rule as the prototype).
- `router/index.ts`: replace the lazy ErrorsPage route at `/errors` with `redirect: "/sessions"`.
- `errors/Index.vue`: delete the dead `!rawSessionId` branch and its styles (its only consumer, `/errors`, is retired); the error workspace becomes the page's only shape.
- Update the affected unit tests (TopNav, App, ui-prototype, router, shell-pages) and the m1-shell E2E.

## Implementation steps

1. Update ui-prototype.test and TopNav.test to failing assertions (two entries, active state, sub-captions).
2. Change `TopNav.vue` and `router/index.ts`; remove the dead branch in `errors/Index.vue`.
3. Sync App.test, router.test, shell-pages.test, and the m1-shell E2E assertions.
4. Run the full frontend gates and the docs gates.

## Dependencies and boundary

- Dependencies: none (the m2 visual system already landed).
- Non-goals: no cross-session error-list page and no new API; no changes to in-page navigation or deep-link formats of Session/Evolution.

## Verification

```sh
pnpm test:web -- TopNav ui-prototype App router shell-pages
```

- All green: exactly two nav entries, `/errors` redirects, and the Session entry stays active on `/sessions/:sid/errors`.

```sh
pnpm verify:flow; pnpm lint:docs; pnpm verify:web-style; pnpm typecheck:web; pnpm lint:web
```

- All green.

```sh
pnpm test:e2e --pattern m1-shell
```

- At 1408 and 390 viewports the nav shows two entries with no horizontal overflow and no console errors; visiting `/errors` lands on `/sessions`.

## Acceptance

- The top bar has exactly two nav items whose copy matches the prototype (including sub-captions); the Session active underline is blue, Evolution purple.
- The Session entry stays active on `/sessions`, `/sessions/:sid`, and `/sessions/:sid/errors`; the Evolution entry stays active on `/evolution/**`.
- Visiting `/errors` redirects to `/sessions`; the "please select a session" placeholder and the parameterless ErrorsPage shape (including the dead code) are removed.
- At 390px there is no horizontal overflow; sub-captions and the note are hidden while nav and user entries stay usable.
- Existing unit tests, E2E, typecheck, lint, verify:flow, and verify:web-style all pass.

## Gates and CI

- `pnpm verify:flow`: the new issue trio and the status machine.
- `pnpm lint:docs`: the new bilingual Agent Note pair.
- `pnpm verify:web-style`: new top-bar styles must take colors from design tokens.
- `pnpm verify:bundle`: removing the `/errors` lazy entry must not regress the first-screen closure.
- `pnpm test:gates`: no gate-script changes; must stay green.

## Non-goals

- No global error list: a cross-session bad-case query is a new backend capability and would need its own issue.
- No changes to the error workspace's structure or interactions (sidebar / flow / dual tabs untouched).
- No brand subtitle change ("轨迹诊断与自进化" is the product tagline; the prototype's "融合原型" was a production-time label without product meaning).
- The Windows entry defect in the `flow-new-issue.mjs` CLI stays out of scope (recorded in m6-05, separate issue).
