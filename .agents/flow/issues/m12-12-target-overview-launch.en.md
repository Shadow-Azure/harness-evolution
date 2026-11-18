# Add a direct launch entry to the target overview

English | [中文](m12-12-target-overview-launch.md)

```yaml flow
kind: issue
id: m12-12
milestone: m12
depends:
  - m11-04
  - m12-06
  - m12-08
priority: P2
status: ready
scope:
  - apps/web/src/pages/overview/**
  - tests/e2e/m11-04-target-overview.test.mjs
  - tests/e2e/m12-12-target-overview-launch.test.mjs
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 339
  url: https://github.com/Shadow-Azure/harness-evolution/issues/339
```

## Background

Production's target overview header exposes only "+ 新增进化对象" and the read-only notice. The V2 prototype shows both "+ 新增进化对象" and "启动自进化" in the same header.

The target overview is where users inspect targets, potential bad cases, and attribution state. Omitting launch forces a return to the evolution list and breaks the path from target distribution to a run.

The gap exists independently of whether a workspace currently has targets: the existing wizard guard already explains missing configuration, so the entry can stay visible and let shared permission and wizard behavior handle empty configuration.

## Goals

- Add "启动自进化" beside "+ 新增进化对象" in the target overview header.
- Reuse the shared launch action introduced by m12-08 and the existing `LaunchWizard`; do not duplicate wizard state.
- Show the action only to management roles and keep read-only roles on the overview.
- With no enabled targets, open the existing configuration guard rather than duplicating target checks.
- Add component and E2E coverage for launch, close, return, and configuration navigation.

## Evidence screenshots

| Production | V2 prototype |
| --- | --- |
| [![Production target overview](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-02-overview-targets.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-02-overview-targets.jpeg) | [![V2 prototype target overview](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-02-overview-targets.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-02-overview-targets.jpeg) |

Both images are real browser-window captures at `2816×1576`. Production offers only "+ 新增进化对象"; the prototype offers both create and launch. Production emptiness reflects a workspace without enabled targets and is not evidence against the action gap.

## Design authority

- [08 §6 Workspace overview](../../../plans/fullstack-design/08-frontend-implementation.md#6-工作空间总览页pagesoverviewindexvuev2): target overview and list entries.
- [08 §8 Evolution list](../../../plans/fullstack-design/08-frontend-implementation.md#8-自进化列表页pagesevolutionindexvue): existing launch entry and wizard ownership.
- [08 §9.1 Launch-wizard state machine](../../../plans/fullstack-design/08-frontend-implementation.md#91-状态机): empty-target guard and four-step flow.
- [V2 design §5.3 Dual views](../../../plans/ui-prototype-v2/design-v2.md#53-双视角bad-case--进化对象): shared target-overview context and actions.
- [V2 design §7 Attribution inside evolution](../../../plans/ui-prototype-v2/design-v2.md#7-归因进入自进化): launching from a target context.

## Implementation

- Add "启动自进化" to the `TargetsOverview` header action group at the same hierarchy as the bad-case overview.
- Consume the shared callback/composable from m12-08, or its query-based activation path, without introducing a second wizard state.
- Reuse the same `canManage` condition as "+ 新增进化对象"; do not add another role predicate.
- Allow the action to open the existing no-target guard and preserve the current workspace when navigating to `/evolution/targets`.
- Test administrator, space administrator, member/read-only, empty targets, wizard close, and return behavior.

## Implementation steps

1. Add failing target-overview action and permission tests.
2. Connect the shared m12-08 launch action and verify no duplicate wizard state is imported.
3. Verify the empty-target guard and current-workspace preservation.
4. Add E2E for launch, close, return, and configuration navigation.
5. Update overview documentation and tests, then run web, E2E, type, and flow gates.

## Dependencies and boundary

- Dependencies: m11-04 supplies the target overview, m12-06 supplies target-validation UX, and m12-08 supplies the shared overview launch action; all must be complete.
- Boundary: add only the target-overview entry wiring; do not change wizard steps, run creation, or target matching.
- Let the existing wizard handle empty configuration; the frontend must not pre-disable based on a duplicated target check.
- Do not add a new configuration modal or evolution route here.

## Verification

```sh
pnpm test:web -- apps/web/src/pages/overview/components/TargetsOverview.test.ts
pnpm test:e2e -- --pattern m12-12
pnpm typecheck:web
pnpm verify:flow
```

- Management roles see the action; read-only roles do not.
- Clicking opens the existing wizard, with the configuration guard shown for empty targets.
- Close and back return to the target overview with filters/window preserved.
- Configuration navigation keeps the current `workspaceId`.

## Acceptance

- The target overview header contains create and launch actions without crowding narrow titles.
- The launch action reuses m12-08/the existing wizard and creates no second step state.
- Permissions, empty configuration, close, and configuration navigation have automated coverage.
- Target stats, trends, filters, pagination, and detail analysis do not regress.
- New tests and docs pass CI.

## Gates and CI

- `pnpm test:web`, `pnpm test:e2e`, `pnpm typecheck:web`, `pnpm verify:bundle`, `pnpm lint:docs`, and `pnpm verify:flow`.
- Include a target-overview header screenshot and assert the action is absent for read-only users.

## Non-goals

- Do not change wizard steps or run APIs.
- Do not execute target matching or attribution inline in the target overview.
- Do not add another target-configuration entry or change configuration-error semantics.
- Do not trap users without targets; preserve the existing configuration guidance.
