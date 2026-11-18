# Align the login page with the V2 prototype information architecture

English | [中文](m12-11-login-v2-layout.md)

```yaml flow
kind: issue
id: m12-11
milestone: m12
depends:
  - m7-03
priority: P2
status: backlog
scope:
  - apps/web/src/pages/login/**
  - apps/web/src/styles/**
  - tests/e2e/m1-shell.test.mjs
  - tests/e2e/m12-11-login-v2-layout.test.mjs
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 338
  url: https://github.com/Shadow-Azure/harness-evolution/issues/338
```

## Background

The production login page is a single roughly 420px card containing a small brand mark, heading, username/password form, and footnote. Most of the viewport is empty.

The V2 prototype uses a roughly 920px two-column card: the left column explains workspace isolation, attribution inside the evolution workflow, and the latest-10 Session behavior; the right column contains the form. The prototype's four account buttons are demo fixtures and must not appear in production because they would enumerate real accounts. Production should adopt the information hierarchy and visual structure without the demo data.

The existing security model still has one global administrator, administrator-created users, forced first-login password changes, and username-based authentication. This issue must preserve those boundaries.

## Goals

- Align the production login page with the V2 two-column layout and collapse to one column on narrow screens.
- Explain product capabilities and workspace/attribution/Session behavior on the left without exposing users, emails, or selectable accounts.
- Preserve username, password, inline errors, loading, and forced-password-change behavior in the form.
- Reuse existing brand, radius, border, spacing, and responsive tokens.
- Cover keyboard order, visible focus, announced errors, and 390px layout.

## Evidence screenshots

| Production | V2 prototype |
| --- | --- |
| [![Production login](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-07-login.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-07-login.jpeg) | [![V2 prototype login](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-07-login.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-07-login.jpeg) |

Both images are real browser-window captures at `2816×1576`. Production is a small single-column card; the prototype uses capability copy on the left and the form on the right. Prototype demo accounts are not a production requirement.

## Design authority

- [08 §4.1 Login and forced password change](../../../plans/fullstack-design/08-frontend-implementation.md#41-登录页与强制改密): username/password, errors, forced change, and return routing.
- [08 §12 Styling and visual implementation](../../../plans/fullstack-design/08-frontend-implementation.md#12-样式与视觉实现): design tokens and Element Plus boundaries.
- [08 §13 Loading, empty, and error states](../../../plans/fullstack-design/08-frontend-implementation.md#13-三态错误与加载): login request states.
- [V2 design §2.2 New pages in the existing V1 visual language](../../../plans/ui-prototype-v2/design-v2.md#22-v2-新增但仍使用-v1-语言): login baseline.
- [V2 design §3 Identity and permissions](../../../plans/ui-prototype-v2/design-v2.md#3-身份与权限): one global administrator, no registration, and member roles.

## Implementation

- Change `pages/login/Index.vue` to a desktop two-column card with brand/capability copy on the left and the form on the right; omit the prototype account list.
- Describe workspace isolation, object-level attribution, and latest-10 Session behavior using static product facts. Never request the user list.
- Keep `LoginForm.vue`, `useLogin`, username/password semantics, errors, loading state, and autocomplete attributes unchanged.
- Reuse existing tokens for width, spacing, radius, and background; at 390px switch to one column and compress the left panel to a short brand/capability summary.
- Add `data-testid` and accessible region headings; Tab order must proceed from capability summary to username, password, and submit.
- Cover normal login, errors, loading, and forced-change entry in component tests, plus desktop/narrow E2E.

## Implementation steps

1. Add failing tests for two-column structure, no account enumeration, and narrow-screen overflow.
2. Refactor the page template and scoped styles without changing login request logic.
3. Replace demo-derived copy with static product facts and hide low-value long copy on mobile.
4. Verify focus, aria, and Tab order while retaining inline `role=alert` errors.
5. Update visual/interaction tests and capture production-build screenshots.
6. Update frontend docs and an Agent Note, then run web, E2E, type, and documentation gates.

## Dependencies and boundary

- Dependency: m7-03 supplies username/Cookie login and session recovery and is done.
- Boundary: presentation and responsive layout only. Do not alter the login API, Cookie, forced-change flow, permissions, or route guards.
- Prototype accounts are visual references only and must not enter production DOM or requests.
- SSO/OIDC remains documented under workspace admin and is not added here.

## Verification

```sh
pnpm test:web -- apps/web/src/pages/login
pnpm test:e2e -- --pattern m12-11
pnpm typecheck:web
pnpm verify:web-style
pnpm verify:bundle
```

- At 1440px the page renders a two-column card; at 390px it is single-column with no horizontal overflow.
- No user list, email list, or account selector appears.
- Username, password, errors, loading, and submit have correct keyboard and aria states.
- Successful login, invalid credentials, and forced-change return behavior remain unchanged.
- Style-token and first-screen bundle gates pass.

## Acceptance

- Production presents the V2 two-column information hierarchy without exposing account enumeration data.
- Username/password login, inline errors, loading, and forced password change do not regress.
- Desktop and 390px screenshots and DOM assertions cover visual and accessibility behavior.
- Colors and spacing use existing tokens only.
- New tests and docs pass CI.

## Gates and CI

- `pnpm test:web`, `pnpm test:e2e`, `pnpm typecheck:web`, `pnpm verify:web-style`, `pnpm verify:bundle`, `pnpm lint:docs`, and `pnpm verify:flow`.
- Include desktop and narrow screenshots and assert that account-list text/DOM is absent.

## Non-goals

- Do not copy prototype demo accounts, emails, or one-click user switching into production.
- Do not change the single-global-admin, user-creation, or forced-change rules.
- Do not implement SSO/OIDC or open registration.
- Do not redesign the application shell or other business pages.
