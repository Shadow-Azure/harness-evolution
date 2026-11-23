# Real patch generation and evaluation execution

English | [中文](m12-03-real-patch-eval.md)

```yaml flow
kind: issue
id: m12-03
milestone: m12
depends:
  - m10-04
  - m12-02
  - m12-20
priority: P1
status: done
scope:
  - apps/api/**
  - scripts/**
  - plans/**
  - docs/**
  - deploy/**
  - .github/workflows/**
  - .agents/flow/**
  - .agents/notes/**
  - packages/contracts/**
adr: []
github:
  number: 244
  url: https://github.com/Shadow-Azure/harness-evolution/issues/244
```

## Background

M12 carries forward the patch and evaluation work scoped in M6 issue #63. The design sections below define the implementation.

## Goals

- Deliver the declared scope and verify it independently.
- Keep contracts, the database and the frontend consistent.
- Define behavior for failures, empty inputs and retries.

## Design authority

- [07 §5.6–5.8 Execution](../../../plans/fullstack-design/07-backend-implementation.md)
- [01 §4.3 Self-evolution](../../../plans/fullstack-design/01-architecture.md)
- [09 R11](../../../plans/fullstack-design/README.md)

## Implementation

- Generate a minimal configuration patch, commit and push the candidate, run evaluation and record the final decision.
- Preserve existing frontend behavior.
- Supply production `HE_EVAL_*` settings to `/opt/harness/shared/.env` through GitHub Secrets and the release workflow.
- Regenerate OpenAPI and TypeScript contracts for the optional iteration patch note.

## Implementation steps

1. Implement the patch and evaluation adapters and an opt-in live test.
2. Run one real Badcase through the full cycle.
3. Record the evidence.

## Dependencies and boundary

- Depends on m10-04, m12-02 and the attribution Golden evaluation gate (m12-20).
- This issue covers patch creation through the acceptance decision.

## Verification

```sh
pnpm test:api -- tests/m12-03-real-patch-eval
pnpm test:db
pnpm contract:check
```

- Verify that one real problem produces a patch, candidate push, evaluation result and acceptance or rejection.
- Existing UI types remain compatible.

## Acceptance

- Trace each decision to its Run, cluster, probe and Badcase.

## Gates and CI

- Run the live integration gate, redaction tests and browser smoke test.

## Non-goals

- Automatic merge into the default branch.
