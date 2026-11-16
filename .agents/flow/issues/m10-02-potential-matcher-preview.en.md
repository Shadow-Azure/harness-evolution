# PotentialMatcher and three-stage preview

English | [中文](m10-02-potential-matcher-preview.md)

```yaml flow
kind: issue
id: m10-02
milestone: m10
depends:
  - m9-03
  - m9-04
  - m9-05
  - m10-01
priority: P0
status: done
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/service/catalogs.py
  - apps/api/app/api/**
  - apps/api/pyproject.toml
  - apps/api/app/db/crud/**
  - apps/api/app/main.py
  - apps/api/app/errors.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
adr: []
github:
  number: 211
  url: https://github.com/Shadow-Azure/harness-evolution/issues/211
```

## Background

Wizard, runs, and overview must share one potential matcher.

## Goals

- Associate skill, agent, and knowledge objects.
- Implement default and custom policy.
- Preview sessions, cases, and cache reuse.

## Design authority

- [07 §5.12、§5.14](../../../plans/fullstack-design/07-backend-implementation.md)：潜在匹配与预览。
- [15 §9.3、§9.5](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：知识触发和里程碑落点。

## Implementation

- Match exact normalized revisions.
- Return explicit unknown reasons.
- Keep preview read-only.

## Implementation steps

1. Write truth-table tests.
2. Implement matcher and paging.
3. Reuse it in prepare.

## Dependencies and boundary

- Dependencies: m9-03, m9-04, m9-05, m10-01
- Boundary: no engine or UI.

## Verification

```sh
pnpm test:api -- tests/m10-02-potential-matcher; pnpm contract:check
```

- Default policy is correct; custom switches and `sameObjectOnly` are correct.
- Revision matches work for knowledge digests and tag-only skills; unknown/non-matching revisions split into `versionUnresolved`/`skipped`.
- Preview is read-only and writes no probe, attribution link, or candidate row.

## Acceptance

- One matcher owns the metric.
- All object kinds share ordering.

## Gates and CI

- API, contract, performance, and flow gates.

## Non-goals

- No fuzzy matching.
- No attribution writes in preview.
