# Target attribution skill configuration API, UI, and run snapshots

English | [中文](m12-attribution-skill-config-ui.md)

```yaml flow
kind: issue
id: m12-21
milestone: m12
depends:
  - m12-06
  - m12-25
  - m12-19
priority: P1
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 319
  url: https://github.com/Shadow-Azure/harness-evolution/issues/319
```

## Background

Target-specific attribution skills become a complete product capability only when users can see the effective source, choose a revision, unbind to fallback, and verify the run snapshot. A backend-only binding would force administrators into database operations and blur workspace defaults, target overrides, and historical run versions.

## Goals

- Add Attribution Skill binding management to evolution-target configuration APIs and UI.
- Show the effective skill source, revision, and cache impact in the launch wizard and run detail.
- Keep historical run snapshots read-only and independent of current target configuration.

## Design authority

- [08 §9.5](../../../plans/fullstack-design/08-frontend-implementation.md): evolution-target configuration UI.
- [05 §4.11 and §4.19–4.20](../../../plans/fullstack-design/05-api-design.md): target, attribution, and run APIs.
- [06 §5.1–5.2](../../../plans/fullstack-design/06-database-design.md): targets and run snapshots.

## Implementation

- Extend target DTOs with effective skill, binding source, revision, state, and compatibility.
- Let workspace admins use default, bind a revision, roll back, or unbind; other roles remain read-only.
- Show the effective skill and cache reuse/invalidation explanation in wizard range and attribution-preview steps.
- Show the immutable snapshot on run cards and attribution detail rather than resolving current bindings for history.
- Reuse the m12-06 git/field diagnosis presentation so the page has one error model.

## Implementation steps

1. Write API/RBAC and component-interaction tests first.
2. Extend target, preview, and run DTOs.
3. Implement binding, fallback, and read-only snapshot presentation.
4. Add E2E, keyboard-accessibility, empty-state, and conflict-error coverage.

## Dependencies and boundary

- Depends on: m12-06, m12-25, and m12-19.
- Boundary: select and display published skill revisions; do not edit or publish skill bodies in the browser.

## Verification

```sh
pnpm test:api -- tests/attribution_skills
pnpm test:web
pnpm typecheck:web
pnpm test:e2e -- --pattern attribution-skill
```

- An admin can bind, roll back, and unbind; members are read-only and viewers cannot write.
- Historical runs always display the effective skill revision captured at launch.

## Acceptance

- The UI clearly distinguishes target override, workspace default, and platform default.
- Incompatible, unpublished, or disabled revisions cannot start a new run and return actionable errors.
- Changing a binding recalculates preview cache counts against the new execution manifest.

## Gates and CI

- API, Web, type, E2E, accessibility, contract, documentation, and Flow gates.

## Non-goals

- Do not implement skill-body editing, arbitrary code upload, an external marketplace, or model-credential management.
- Do not change attribution algorithms, Session matching, or clustering.
