# M22 Attribution list version labels aligned with the V2 prototype

English | [中文](m22-milestone.md)

```yaml flow
kind: milestone
id: m22
title: M22 归因列表版本显示与 V2 原型对齐
status: done
github:
  number: 31
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/31
```

## Goals

Converge the version label in the Session error view's attribution list from the content digest to the readable ref + short commit used by the overview. Historic attributions with only digest evidence keep a digest fallback that truncates, reveals the full value on hover, and offers one-click copy, so a long version cannot squeeze out the object name or overlap status badges. The prototype lands first; the production API and frontend follow.

## Scope

`plans/ui-prototype-v2/harness-evolution.html`, the error-detail attribution-list API contract and read path, `apps/web/src/pages/errors/**`, contract generation, API / component / E2E tests, the Agent Note, design document 08 §7.1, and the matching flow files. Later display drift in the attribution-list version label follows this milestone; the low-content fill and flow placeholder of the Session browser shell on the same page are delivered with this milestone as well.

## Acceptance

When a ref exists the attribution item shows the ref + short commit; commit-only input shows the short commit; digest-only input keeps a truncated digest fallback. A long version does not squeeze out the object name or overlap the cache / conclusion badges. Hovering a truncated value reveals the full value above it, and the copy button copies the full version identifier. The prototype change includes same-viewport Before / After screenshots. Attribution matching, cache keys, statistics, and conclusion semantics stay unchanged.

## Non-goals

No change to `digest:<sha256>` as the canonical matching and cache key; no reverse lookup of git refs for historic digest-only attributions; no reordering of other attribution fields or change to pagination; no production Session content or screenshots committed to the repository.
