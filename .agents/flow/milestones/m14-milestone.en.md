# M14 Problem-card display aligned with the prototype

English | [中文](m14-milestone.md)

```yaml flow
kind: milestone
id: m14
title: M14 问题卡展示与原型对齐
status: done
github:
  number: 22
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/22
```

## Goals

Close the display drift that V2 prototype acceptance exposed: the Session page problem card leads with the problem description and carries the type/object badges, full case ID, association row, and locate affordance, while the attribution state stays a lightweight marker.

## Scope

The non-compact template and styles of the Session page problem list card, its unit and E2E tests, the matching V2 prototype rendering, the design document, and evidence screenshots. Later display drift of the same kind follows this milestone. Known open item: type badge color and fill follow the error detail page and stay opposite to the prototype stylesheet.

## Acceptance

List cards for both unanalyzed and analyzed cases show the problem description; every card carries the BC number, type/object badges, full case ID, association row, and "定位 ↗"; the error detail page, API, data model, and attribution logic stay unchanged; focused gates and before/after screenshots are present.

## Non-goals

No rework of the problem list information architecture, no change to the attribution state machine, API, data model, or error detail page, and no production Session content committed to the repository.
