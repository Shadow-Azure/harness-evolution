# M2 Trace data and normalization

English | [中文](m2-milestone.md)

```yaml flow
kind: milestone
id: m2
title: M2 轨迹数据与归一化
status: done
github:
  number: 10
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/10
```

## Goals

Turn payload ingestion, parsing, agent trees, and idempotent queries into a verifiable data base.

## Scope

Fixtures, local import, normalization, trees, replay, API, and scheduling

## Acceptance

Four local sessions import to SQLite; repeat imports have no side effects; API stats match.

## Non-goals

No graph UI or problem cards.
