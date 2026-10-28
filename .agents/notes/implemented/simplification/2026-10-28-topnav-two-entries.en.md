# Agent Note: Top-nav information architecture restored to the prototype's two entries

Status: implemented

English | [中文](2026-10-28-topnav-two-entries.md)

## Problem

The m1-09 scaffold introduced the Sessions/Errors/Evolution trio plus a top-level `/errors` route as placeholders (its own test said "top-level errors entry arrives later"), and m2-09 aligned only the prototype's visual system, cementing "Sessions/Errors/Evolution underline navigation" into acceptance. The prototype's information architecture, however, has two entries: error detail is a sub-page inside the Session view. The result is that the top-level Errors entry became a dead end — `/errors` rendered only a "please select a session" empty state with no cross-session error-list API behind it and no actionable way out. Additionally, no nav item was active on `/sessions/:sid` or `/sessions/:sid/errors` (vue-router's `router-link-active` matches route records, not path prefixes, and these are flat sibling records), contradicting the prototype where the Session tab stays active across sub-pages.

## Decision

- The top bar keeps exactly two entries: Session 错误查看 (sub-caption "会话轨迹与归因") and 自进化 (sub-caption "报告驱动的迭代优化"), with the ID cross-link note on the right; sub-captions and the note hide below 1100px (same rule as the prototype).
- The active state is computed inside TopNav from the path prefix (`/sessions*` → blue, `/evolution*` → purple) instead of `router-link-active`; the flat route structure stays untouched.
- The top-level `/errors` route is retired into `redirect: "/sessions"`; ErrorsPage's parameterless empty-state branch and its styles are removed, making the error workspace the page's only shape. Error detail's only entries are the Session cards/overview and evolution deep links `/sessions/:sid/errors?case=&tab=`.

## Alternatives considered

- Keep three entries and make Errors a real page: it needs a new cross-session bad-case list API and contract changes, while the design docs (F1 "switching between the two views"; the route table registers only `/sessions/:sid/errors`) never supported a top-level `/errors`. Building backend capability for a nav placeholder is not worth it. No — retire the entry first; file a new issue when the need is real.
- Restructure routes as nested (`/sessions` parent with `:sid` and `:sid/errors` children) so `router-link-active` works naturally: it requires a pass-through parent component rendering only `<RouterView/>` plus workspace-meta and restore-path bookkeeping — far more churn than the benefit. No — computing the prefix inside TopNav is enough.
- Make `/errors` render the error workspace with the first session auto-selected: still a context-free dead page and contradicts the prototype's "error detail belongs to the Session view". No.

## Consequences

- Old bookmarks and external links to `/errors` land on `/sessions` instead of a placeholder; the evidence script `reports/2026-10-26/m4-04-error-detail/collect-smoke.mjs` that visits `/errors` will land on Sessions (historical evidence script, intentionally not updated by this change).
- The nav contract locked by `ui-prototype.test` changed from three entries to two; any future top-level view (e.g. a standalone timeline page) must update that contract and this note together.
- A cross-session error overview remains a product blank: if it becomes real, do it in a new issue (API + contract + page together) and do not reuse the `/errors` path.
