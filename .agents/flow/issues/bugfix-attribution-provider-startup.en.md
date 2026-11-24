# Start attribution with the shared AI agent provider and inherit its model

English | [中文](bugfix-attribution-provider-startup.md)

```yaml flow
kind: issue
id: bugfix-41
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - apps/api/**
  - apps/web/**
  - tests/e2e/**
  - .env.example
  - plans/**
  - .agents/**
  - AGENTS.md
  - scripts/gates.spec.mjs
  - scripts/run-e2e.mjs
  - docs/deployment*
adr: []
github:
  number: 542
  url: https://github.com/Shadow-Azure/harness-evolution/issues/542
```

## Background

Bindings can already be pending when the API starts. A separate attribution switch prevents the consumer from claiming them even when the shared Claude provider is configured. Attribution also selects its own default model.

## Goals

Enable binding attribution and wizard recomputation from the shared provider's Skill capability and model selection.

## Design authority

[Attribution preview and target binding](../../../plans/fullstack-design/02-features.md)

## Implementation

Expose Skill capability and the default model through the shared provider. Freeze the provider and model for new batches and preserve execution of historical snapshots.

## Implementation steps

1. Unify startup, binding and wizard availability.
2. Project shared model settings into the isolated Claude invocation and update operator and UI guidance.
3. Verify startup claims a persisted binding and writes a report.

## Dependencies and boundary

Use the existing queue, lease and report tables.

## Verification

```sh
pnpm test:api
pnpm test:web
```

## Acceptance

Skill-capable providers automatically process pending bindings. Analysis-only providers retain access to existing reports. New snapshots record the shared model and historical snapshots can run with their original model.

## Gates and CI

Run API, web, flow and documentation checks.

## Non-goals

Production rollout and historical report recomputation are independent operations.
