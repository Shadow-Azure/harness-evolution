# Engineering and flow baseline

English | [中文](m0-docs-gates.md)

```yaml flow
kind: milestone
id: m0
title: 工程与流程基线
status: done
github:
  number: null
  url: null
```

## Goals

Wire the pnpm workspace, web and server shells and health check, and land documentation engineering, PR review and the roadmap → milestone → issue gates.

## Acceptance

- `pnpm build`, `pnpm typecheck` and the health check work.
- Documentation layering, bilingual pairing, Agent Notes and the flow tree are complete.
- `pnpm verify:docs` and `pnpm verify:flow` are green and wired into CI.

## Issues

- [Documentation, review and flow gate system](../issues/m0-01-docs-gate-system.en.md)
