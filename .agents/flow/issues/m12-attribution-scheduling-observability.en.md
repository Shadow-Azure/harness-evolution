# Attribution scheduling, retries, and runtime observability

English | [中文](m12-attribution-scheduling-observability.md)

```yaml flow
kind: issue
id: m12-20
milestone: m12
depends:
  - m12-17
  - m12-18
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
  number: 318
  url: https://github.com/Shadow-Azure/harness-evolution/issues/318
```

## Background

The existing intranet attribution process handles reported bad cases in scheduled batches, while the repository currently invokes attribution serially inside evolution-run preparation. A real agent call may take tens of seconds and incur retries, tokens, and rate limits. Keeping it under the global serial worker would block sync and other runs, while separate manual, scheduled, and recovery paths would drift into three execution semantics.

## Goals

- Reuse one attribution service and execution manifest across user launches, schedules, and failure retries.
- Support Session-level context reuse, bounded bad-case concurrency, idempotent claims, and recoverable state.
- Expose throughput, cache, latency, token, error, and evidence-coverage observability.

## Design authority

- [04 §7.2 and §8](../../../plans/fullstack-design/04-backend-architecture.md): job truth, the serial worker, and expansion paths.
- [07 §5.11–5.13](../../../plans/fullstack-design/07-backend-implementation.md): prepare, the attribution runner, and events.
- [06 §5.8–5.9](../../../plans/fullstack-design/06-database-design.md): attribution cache and candidate snapshots.

## Implementation

- Implement durable claim, lease, timeout, retry, cancellation, and concurrency limits on job/execution records.
- Assemble context once per Session and process its bad cases with bounded concurrency; every trigger shares idempotency keys and cache.
- Review and choose either an `attribution_only` run mode or reuse of `cluster_only`, retaining one official scheduled entry point.
- Record executor, skill/model revision, context hash, latency, tokens, retries, cache state, and warning metrics.
- Expose progress, failure reasons, and per-item retry while excluding raw traces, skill bodies, and secrets from logs and metrics.

## Implementation steps

1. Write tests for duplicate scheduling, worker restart, expired leases, partial success, and rate limits.
2. Implement the durable execution queue and Session-batch orchestration.
3. Connect manual, scheduled, and retry entries plus progress reads.
4. Add metrics, alerts, redaction, and operations documentation.

## Dependencies and boundary

- Depends on: m12-17 and m12-18.
- Boundary: productionize scheduling and observability for quality-gated attribution engines; do not alter attribution algorithms or promotion decisions.

## Verification

```sh
pnpm test:api -- tests/attribution_jobs
pnpm test:db
pnpm test:db:mysql
pnpm test:e2e -- --pattern attribution-jobs
```

- Duplicate triggers produce one effective execution, and process restart resumes from durable state.
- One failed bad case does not overwrite completed reports in the same Session, and retry processes only unfinished items.

## Acceptance

- Manual, scheduled, and run-prepare paths share cache and idempotency semantics for the same execution manifest.
- Slow LLM calls do not retain the current global worker lock or block trace synchronization.
- Administrators can inspect throughput, failures, latency, tokens, cache, and warnings without sensitive-content leakage.

## Gates and CI

- API, dual-database, restart-recovery, concurrency, E2E, redaction, documentation, and Flow gates.

## Non-goals

- Do not introduce a second report system, second cache, or trigger-specific algorithms.
- Do not allow unbounded concurrency, infinite automatic retries, or automatic promotion of skills that failed quality gates.
