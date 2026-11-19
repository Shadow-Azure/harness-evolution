# M17 Target-card version labels aligned with the V2 prototype

English | [中文](m17-milestone.md)

```yaml flow
kind: milestone
id: m17
title: M17 对象卡版本显示与 V2 原型对齐
status: done
github:
  number: 25
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/25
```

## Goals

Show readable git refs and short commits in the single-target analysis version rows and multi-select instead of content digests, merge ref and digest evidence of one version into a single row, and keep a digest fallback for history that has no ref evidence.

## Scope

Version discovery and aggregation in the target overview, run-backed version evidence, the target-detail contract, version rendering in the overview target card and side list, unit and browser E2E coverage, the Agent Note, and flow files.

## Acceptance

- A version that came from a tag, branch, or commit id shows that ref in both the version rows and the multi-select, with the short commit when a run recorded one.
- A version recorded as both ref and digest appears once, prefers the ref, and is not double counted.
- Digest-only historical versions stay visible without losing counts; version filtering, Session association, attribution, and cache semantics are unchanged.
- Before/after captures are comparable with the same V2 prototype region, and the PR description carries both.

## Non-goals

No change to the PotentialMatcher, attribution cache keys, or Session association; no git-ref backfill for digest-only history; no restyling of other target-card regions and no new version-filter interaction.
