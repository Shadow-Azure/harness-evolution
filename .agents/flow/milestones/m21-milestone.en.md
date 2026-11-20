# M21 Run detail aligned with the prototype

English | [中文](m21-milestone.md)

```yaml flow
kind: milestone
id: m21
title: M21 运行详情与原型对齐
status: active
github:
  number: 29
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/29
```

## Goals

Converge the "Evolution → Run detail" page hierarchy, field set, and counting back to the V2 prototype and design document 08 §10: the header keeps only title, status, and workspace badge; workspace, push, and eval information move into the "Goal and input" collapsible area; "Flow progress" follows "Goal and input" and the current step output follows it; the execution-log tab and preparing state are visible in both production and the prototype.

## Scope

`apps/web/src/pages/evolution/RunDetail.vue` and its component tests, `tests/e2e/m10-06-run-detail-v2.test.mjs`, `plans/ui-prototype-v2/harness-evolution.html`, `plans/fullstack-design/08-frontend-implementation.md`, and the matching flow files and Agent Note. Later display drift between the run detail and the V2 prototype follows this milestone.

## Acceptance

The header shows title + status + workspace badge; goal and input shows workspace, associated Sessions, bad cases in window, potential bad cases, attributed / non-target, and policy/cache badges; workspace information sits in the workspace collapsible area and the branch name stays copyable; flow progress follows goal and input; the distribution title and legend use the potential-bad-case wording; the seven-step / execution-log tabs and the preparing state are visible in production and the prototype; the API contract and execution algorithms stay unchanged; focused gates and before / after screenshots are present.

## Non-goals

No change to attribution, clustering, eval algorithms, API contract, SSE, seven-step keys, or pagination; no change to step content components, the evolution list, launch wizard, or target config; no production Session content or screenshots committed to the repository.
