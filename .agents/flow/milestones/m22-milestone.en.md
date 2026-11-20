# M22 Run list aligned with the prototype

English | [中文](m22-milestone.md)

```yaml flow
kind: milestone
id: m22
title: M22 运行列表与原型对齐
status: active
github:
  number: 32
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/32
```

## Goals

Complete the run-configuration facts on "Evolution → History" run cards to match the V2 prototype and design document 05 §3.5: after the target version and time window, show workspace, potential policy, and cache labels; the card no longer prefixes the creator, which stays in the DTO; the history card structure and its six statistics do not regress.

## Scope

`apps/api/app/service/evolution/runs.py` and its tests, `packages/contracts` generated artifacts, `apps/web/src/pages/evolution/**`, `tests/e2e/**`, `plans/ui-prototype-v2/harness-evolution.html`, `plans/fullstack-design/05-api-design.md` and `08-frontend-implementation.md`, `scripts/doc-budgets.manifest.json`, plus the matching flow files and Agent Note. Later display drift between the run list and the V2 prototype follows this milestone.

## Acceptance

History cards show target version, time window, workspace, default / custom potential policy, and reuse / no-reuse cache in prototype order; the contract carries backend-projected `policy.preset` and `cacheEnabled`, with legacy runs without a policy shown as default; the card's top-right meta shows only the time and the creator stays in the DTO without list rendering; completed runs keep the best / initial / Δ / accepted line and failed runs do not invent final data; contract, types, unit tests, API tests, and focused E2E pass; before / after screenshots share one viewport and are attached to the PR.

## Non-goals

No change to the run detail page, launch wizard, target configuration, or attribution step content; no change to the database schema, attribution / clustering / eval algorithms, SSE, seven-step keys, or pagination; no list-page layout or page-width rework; no production Session content or screenshots committed to the repository.
