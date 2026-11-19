# Keep the error-detail shell for trace-less bad cases

English | [中文](m12-bad-case-trace-shell.md)

```yaml flow
kind: issue
id: m12-15
milestone: m12
depends:
  - m12-07
priority: P1
status: done
scope:
  - apps/web/src/pages/errors/**
  - tests/e2e/m12-07-trace-state.test.mjs
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
adr: []
github:
  number: 357
  url: https://github.com/Shadow-Azure/harness-evolution/issues/357
```

## Background

m12-07 turned "a bad-case row exists but its Session is not projected yet" from `404 BAD_CASE_NOT_FOUND` into `409/503` plus `TraceStatusPanel`, and the overview list and API semantics are aligned. The error-detail page, however, implements the state branch as a whole-page replacement: `trace-mode` renders only one centered status panel, while `ErrorSidebar` and `error-head` stay in the `v-else` branch. Users therefore cannot see the current case, object, report time, or attribution state, and they lose shell actions such as "Back to Session". The V2 prototype replaces only the flow and detail tabs inside `<main>` while always keeping the sidebar and header, so the production information architecture diverges from the prototype at 1440px (issue #357).

## Goals

- Keep the 340px sidebar and `error-head` in `trace-mode`; replace only the execution flow and the description/attribution tabs with `TraceStatusPanel`.
- With no Session, show case-scoped content in the sidebar: title, `syncStatus` badge, bad-case ID, object name, and either the attribution empty state or the count; do not fabricate other cases in the Session.
- `error-head` shows the root Session ID, report time (`details.createdAt`), object name, `1 bad case`, and the attribution count.
- "Back to Session" is available only when the Session is readable; without a Session render a disabled control so no new 404 dead link appears.
- Keep the 409/503/404 codes, the `details` payload, and list status fields unchanged; the ready detail page must not regress.

## Design authority

- [08 §7 Error detail page](../../../plans/fullstack-design/08-frontend-implementation.md#7-错误详情页pageserrorsindexvue): the 340px sidebar + `error-head` + flow + two-tab layout and its data sources.
- [05 §3.8.1 bad-case trace state](../../../plans/fullstack-design/05-api-design.md#381-bad-case-轨迹状态): 409/503, the `details` fields, and 404 semantics.
- [V2 prototype error detail](../../../plans/ui-prototype-v2/harness-evolution.html): `traceUnavailable` replaces only the flow and detail tabs inside `<main className="err-main">`.
- [2026-11-17 trace state for bad cases without a Session](../../notes/implemented/bug-fix/2026-11-17-bad-case-session-trace-status.en.md): trace-state derivation and detail error codes.

## Implementation

- Adjust `pages/errors/Index.vue`: move `ErrorSidebar` and `error-head` outside the state branch; when `traceStatus` exists render the status panel inside `<main>` instead of collapsing to one column.
- Extend `ErrorSidebar`: add `trace` and attribution-state inputs; without a Session show the current case title, ID, object name, `syncStatus` badge, and attribution empty state or count; disable "Back to Session" when there is no Session.
- In the trace branch, `error-head` uses `details.createdAt`, `details.objectName`, the route `sid`, and the attribution endpoint `total`, and also disables the back entry when no Session exists.
- Update component tests to cover pending/unavailable states where the sidebar, header, and status panel coexist, the flow/tabs do not render, and the attribution count is shown.
- Extend `tests/e2e/m12-07-trace-state.test.mjs` to assert the shell and disabled back entry at 1440×960.
- Add no case read endpoint: the acceptance fields already come from the 503 `details`, the route `sid`, and `GET …/bad-cases/{id}/attributions`.

## Implementation steps

1. Refactor the `Index.vue` template and `trace-mode` styles to keep the two-column layout and header.
2. Add the case-scoped branch and attribution-state display to `ErrorSidebar`.
3. Update `Index.test.ts`, related `TraceStatusPanel` tests, and the `m12-07` E2E assertions.
4. Run the Web unit tests, typecheck, lint, and `m12-07` E2E; capture 1440px comparison screenshots.
5. Update the Agent Note and PR evidence, then wait for CI and review.

## Dependencies and boundary

- Depends on m12-07's trace-state derivation and the `BAD_CASE_SESSION_PENDING` / `BAD_CASE_SESSION_UNAVAILABLE` error codes.
- Boundary: only the Web error-detail page and its tests, flow/notes, and review documents change; the backend read model, error codes, scheduling policy, and overview do not.
- Without a Session the page does not list sibling cases from the same root; that needs a new case-level read model and is out of scope here.

## Verification

```sh
cd apps/web && pnpm exec vitest run src/pages/errors/Index.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- --pattern m12-07-trace-state
```

- Component tests: under pending/unavailable, `.error-sidebar`, `.error-head`, and `[data-testid=trace-status-panel]` exist, while `role=tab` and `.sidebar-filter` are absent and the execution flow is not rendered.
- E2E: after opening an unready case from the overview, the sidebar contains the case title and root Session ID, the header contains `1 bad case` and the object name, and Back to Session is disabled.
- Screenshots: at 1440×913 in the light theme, the unready detail shows the two-column shell + status panel like the prototype, compared side by side with `proto-after-detail.png` from issue #357.

## Acceptance

- The `View` page of an unready case contains the error-detail sidebar, error-detail header, and trace status panel; the flow, description, and attribution tabs do not render.
- `error-head` shows the root Session ID, report time, object name, `1 bad case`, and attribution count; the page is no longer a single centered panel.
- "Back to Session" is available only when the Session is readable; without a Session there is no new 404 dead link.
- The ready case detail keeps its sidebar, flow, two tabs, and original back entry.
- The Session-dimension endpoint still returns 409/503 with the original `details`; a genuinely missing case still returns 404; list status fields are unchanged.

## Gates and CI

- `pnpm lint:web`, `pnpm typecheck:web`, `pnpm test:web`.
- `pnpm test:e2e -- --pattern m12-07-trace-state` (CI e2e lane).
- `node scripts/verify-flow.mjs --diff origin/main` and `pnpm test:gates`.
- `pnpm verify:docs` (bilingual pairing for Agent Notes and flow files).

## Non-goals

- Do not change trace-state mapping, 409/503/404 codes, or scheduling/retry policy.
- Do not add a case-detail read endpoint or extend the 503 `details` contract.
- Do not redesign the overview or error-detail visuals, and do not restore the removed timeline page.
- Do not address the login-state/HTTPS problem in #348.
