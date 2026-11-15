# Four-step launch wizard and launch integration

English | [中文](m10-05-four-step-launch-wizard.md)

```yaml flow
kind: issue
id: m10-05
milestone: m10
depends:
  - m10-02
  - m10-03
  - m7-08
priority: P1
status: backlog
scope:
  - apps/web/src/pages/evolution/**
  - apps/web/src/api/**
  - apps/web/src/composables/**
  - tests/e2e/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 214
  url: https://github.com/Shadow-Azure/harness-evolution/issues/214
```

## Background

Users need a staged preview before launching cluster-only or full evolution.

## Goals

- Implement four wizard steps.
- Support case-focused entry.
- Route accepted runs correctly.

## Design authority

- [08 §9](../../../plans/fullstack-design/08-frontend-implementation.md)：启动向导。
- [05 §4.20](../../../plans/fullstack-design/05-api-design.md)：预览与启动端点。

## Implementation

- Load targets by workspace.
- Validate custom policy.
- Refresh cache preview on toggle.

## Implementation steps

1. Write state tests.
2. Build forms and previews.
3. Add launch E2E.

## Dependencies and boundary

- Dependencies: m10-02, m10-03, m7-08
- Boundary: no run detail.

## Verification

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern launch-wizard-v2
```

- Inputs do not recompute earlier steps.
- Empty states block progress.
- Both exits route correctly.

## Acceptance

- Prototype IA is met.
- The frontend does not duplicate matching.

## Gates and CI

- Web, E2E, bundle, and flow gates.

## Non-goals

- No model selection.
- No attribution during the wizard.
