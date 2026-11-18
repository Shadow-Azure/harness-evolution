# Restore V2 overview workflows and operational context

English | [中文](m12-08-overview-v2-actions-context.md)

```yaml flow
kind: issue
id: m12-08
milestone: m12
depends:
  - m7-09
  - m8-04
priority: P1
status: ready
scope:
  - apps/web/src/pages/overview/**
  - apps/web/src/pages/evolution/**
  - tests/e2e/m8-04-overview.test.mjs
  - tests/e2e/m12-08-overview-actions-context.test.mjs
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 335
  url: https://github.com/Shadow-Azure/harness-evolution/issues/335
```

## Background

The 2026-11-17 production-versus-prototype comparison shows that the overview shell is aligned, but production omits both V2 workflow entry points and the operational context that the prototype places beside the trend chart.

Production shows only the read-only address-state notice in the page header and lets the trend chart consume the full width. The prototype exposes "上报接入" and "启动自进化" together and pairs the trend with workspace quota, ingest access, and current-workspace context, plus an expandable source-by-time breakdown.

The captured production workspace contains 9 bad cases, 1 source, and 9 related Sessions; the prototype contains 26 bad cases, 7 sources, and 11 related Sessions. Data-volume differences are out of scope. This issue addresses only data-independent actions, permission gating, and page structure.

## Goals

- Add "上报接入" and "启动自进化" to the bad-case overview header while hiding write actions from unauthorized roles.
- Reuse the existing workspace-admin route and launch wizard rather than introducing another write path or state machine.
- Restore workspace quota, ingest address, and current-workspace context beside the trend, with a stacked layout on narrow screens.
- Return the source-by-time detail entry to the overview analytics area while preserving explainable URL filter state.
- Add component and E2E coverage for actions, empty data, permissions, and responsive layout.

## Design authority

- [08 §6 Workspace overview](../../../plans/fullstack-design/08-frontend-implementation.md#6-工作空间总览页pagesoverviewindexvuev2): overview data, chart, filters, and three-state behavior.
- [08 §4.2 Top-bar user area, workspace switcher, and admin page](../../../plans/fullstack-design/08-frontend-implementation.md#42-顶栏用户区空间切换器与空间管理页v2): workspace roles and entry permissions.
- [08 §8 Evolution list](../../../plans/fullstack-design/08-frontend-implementation.md#8-自进化列表页pagesevolutionindexvue): reuse the existing launch flow.
- [05 §4.16 Workspaces, members, and credentials](../../../plans/fullstack-design/05-api-design.md#416-工作空间成员与凭据v2): quota and credential read boundaries.
- [V2 design §5 Workspace overview](../../../plans/ui-prototype-v2/design-v2.md#5-工作空间总览): prototype actions, metrics, side context, and drill-down behavior.

## Implementation

- Add "上报接入" and "启动自进化" to `apps/web/src/pages/overview/Index.vue`; link to the current workspace's `admin?tab=ingest` and open the existing `LaunchWizard`.
- Gate actions with `canManageWorkspace(currentRole)` and the write-permission matrix; do not render bypassable empty links.
- Add an operational-context region using existing overview/workspace summary data for quota, source count, and workspace identity; derive the ingest address from the current workspace ID instead of duplicating credential rules.
- Add a source-by-time disclosure to the source-distribution card using the already-loaded overview data, without an unconstrained extra scan.
- Keep global filters in place; list-local filters remain owned by m12-09 to avoid conflicting URL state.
- Reuse existing `statstrip`, `card`, `chip`, and responsive tokens; place context after trends and lists on narrow screens.
- Cover admin, space-admin, member, and read-only permission branches in unit tests, plus real navigation and return behavior in E2E.

## Implementation steps

1. Add failing snapshots for header actions, permission branches, and empty data.
2. Promote the launch action to the overview and reuse workspace identity, role checks, and existing routes.
3. Add operational context using existing workspace/overview queries and avoid duplicate requests.
4. Restore the source-by-time detail toggle and test expanded, collapsed, and empty states.
5. Tune 1440px, 1024px, and narrow layouts and add E2E navigation assertions.
6. Update architecture/frontend docs and an Agent Note, then run focused and full gates.

## Dependencies and boundary

- Dependencies: m7-09 supplies the admin page and m8-04 supplies the overview body; both are done.
- Boundary: this issue adds only overview actions and operational context. It does not change quota, credential, member, or evolution-run semantics.
- No schema or API addition is planned. If existing responses are insufficient, reuse workspaces/overview endpoints and isolate any narrow response addition as an explicit subtask.
- List-local date/source/type filters belong to m12-09 and trigger-point data belongs to m12-10.

## Verification

```sh
pnpm test:web -- apps/web/src/pages/overview/Index.test.ts
pnpm test:e2e -- --pattern m12-08
pnpm typecheck:web
pnpm verify:bundle
```

- An administrator sees both actions and the operational context.
- The actions reach `admin?tab=ingest` and the launch wizard for the current workspace; return preserves filters.
- Users without management permission see no write actions while member read access remains available.
- E2E covers 1440px and narrow layouts with no horizontal overflow.
- `verify:bundle` does not pull the new entry points into unrelated first-screen chunks.

## Acceptance

- The bad-case overview exposes both V2 workflow actions with correct workspace-role gating.
- Quota, ingest address, and workspace context form a right-side context on desktop and stacked cards after primary content on narrow screens.
- The source-by-time detail reflects active filters and shows an honest empty state.
- All actions reuse existing pages/routes and preserve overview URL state on return.
- New tests and docs pass CI with no regression to statistics, trend, list, or pagination.

## Gates and CI

- `pnpm test:web`, `pnpm test:e2e`, `pnpm typecheck:web`, `pnpm verify:bundle`, `pnpm lint:docs`, and `pnpm verify:flow`.
- PR evidence must include production/prototype screenshots or DOM assertions; role behavior must cover at least administrator and read-only member.

## Non-goals

- Do not change server-side quota, membership, or credential rules.
- Do not seed the prototype's 26 bad cases or fixed workspace names into production fixtures.
- Do not implement list-local filters or trigger-point columns here.
- Do not restore the retired timeline page.
