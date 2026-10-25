# Agent Note: Vue shell and frontend quality gates

Status: implemented

English | [中文](2026-10-25-vue-shell-quality-gates.md)

## Problem

The React development shell lacked routed empty views, a shared query data layer, and token constraints. Front-end quality was left mainly to tests and builds; Vue Flow could enter the first-screen closure and hard-coded colors could not be rejected mechanically.

## Decision

- Rebuild `apps/web` with Vue 3, Vue Router, Pinia, and TanStack Query. `/sessions` stays synchronous on first screen, while `/evolution` lazy-loads and isolates Vue Flow in a vendor chunk.
- The frontend runs ESLint, `vue-tsc`, Vitest with jsdom, V8 coverage at 80% across four metrics, MSW test services, token color scanning, and Vite manifest bundle-boundary checks.
- The shared HTTP layer normalizes network failures, rejected statuses, and malformed JSON into `ApiError`; health's contractual 503 is not mistaken for a network failure.
- CI explicitly runs gate self-tests, frontend lint/type/tests, and token and bundle guards; cross-stack integration continues to verify the real proxy, FastAPI, and shared contracts.

## Alternatives considered

- Continue patching React: smaller now, but diverges from the chosen Vue ecosystem and later Vue Flow design; rejected.
- Treat lint, bundle, and style checks as advisory documentation: easy to bypass and unable to prevent first-screen regressions; rejected in favor of actual CI execution.

## Consequences

- Frontend changes must pass lint, type, coverage, integration, token, and bundle gates; Vue Flow in the first screen or hard-coded colors fails.
- New business pages default to route-level lazy loading and the shared HTTP/query layer; domain pages continue in later issues.
- MSW remains limited to test dependencies and test code; runtime requests use the shared HTTP layer directly.
