# Vue 3 shell and frontend gates

English | [中文](m1-05-web-shell.md)

```yaml flow
kind: issue
id: m1-05
milestone: m1
depends:
  - m1-04
priority: P0
status: in-progress
scope:
  - AGENTS.md
  - apps/web/**
  - packages/contracts/**
  - package.json
  - pnpm-lock.yaml
  - scripts/**
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
adr: []
github:
  number: 28
  url: https://github.com/Shadow-Azure/harness-evolution/issues/28
```

## Background

The prototype interaction needs Vue Flow, Pinia/Query, and unified tokens; establishing the correct skeleton first avoids rework in later pages.

## Goals

- Rebuild `apps/web` with Vue 3, router, Pinia, TanStack Query, and design tokens.
- Establish node/jsdom Vitest, ESLint, vue-tsc, bundle boundaries, and build guards.
- Make two empty views navigable with contract types checked at compile time.

## Design authority

- [03 Frontend architecture](../../../plans/fullstack-design/03-frontend-architecture.md)
- [08 Frontend implementation](../../../plans/fullstack-design/08-frontend-implementation.md)

## Implementation

- Lazy-load non-default routes; Vue Flow must not enter the first-screen closure.
- Make `tokens.css` the only color source and reject hard-coded component colors.
- Keep MSW test-only, with no mock branch in runtime code.

## Implementation steps

1. Write failing route, token, health API, and bundle-guard tests first.
2. Create the App/TopNav/router/query/http skeleton and remove React.
3. Wire lint/type/test/build and `verify:bundle` into local and CI gates.

## Dependencies and boundary

- Depends on m1-04.
- Delivers only a navigable empty shell and shared data layer; login and domain pages are out of scope.

## Verification
```sh
pnpm test:web
pnpm typecheck:web
pnpm lint:web
pnpm build
pnpm verify:bundle
pnpm verify:web-style
```

- The first-screen bundle excludes Vue Flow; boundary violations fail after build.
- Component and API tests pass with the shared real-response contract fixtures.

## Acceptance

- `pnpm dev:web` opens the empty-state navigation.
- React files are removed and the build succeeds.

## Gates and CI

- Frontend lint/type/test/build/bundle, token checks, and CI gate self-tests run in CI.

## Non-goals

- No login, sessions, graph, or evolution UI.
