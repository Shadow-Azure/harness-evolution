# M2 Real trace service: session family import and storage

English | [中文](m2-trace-service.md)

```yaml flow
kind: milestone
id: m2
title: M2 真实轨迹服务：Session Family 导入与存储
status: planned
github:
  number: 6
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/6
```

## Goal

Replace prototype data with a deterministic import and query service for local rollouts.

## Scope

- Stream JSONL while retaining raw records and normalized views
- Assemble session families by parent_thread_id with depth and agent paths
- SQLite migrations, repositories and session/family/ingest/timeline APIs
- Idempotent rescans and replayable parse failures

## Acceptance

- All 64 rollouts across the four root families import completely
- Repeated imports add no duplicate sessions, turns or items
- API results for families, agent trees and timelines match prototype fixtures
- Files above 20MB and sessions above 3,000 records stream without blocking

## Non-goals

- Multi-user access, permissions or a production database
- AI diagnosis or automatic improvements
