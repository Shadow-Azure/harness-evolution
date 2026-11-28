# M29 Trace payload tiered storage

English | [中文](m29-milestone.md)

```yaml flow
kind: milestone
id: m29
title: M29 轨迹原始负载分层存储
status: planned
github:
  number: 39
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/39
```

## Goals

- Reduce the primary-database footprint of `trajectory_payloads` without losing raw evidence or replay ability: compress payloads first, then tier low-frequency payloads to object storage.
- `trajectory_payloads` remains the single source of truth for raw traces; normalization, idempotent replay, and reads by `(runtime_key, root_session_id, agent_id)` keep their semantics.
- Upstream re-download is only an optional recovery path when an object is missing, never the sole copy; `script` sources must not depend on it.
- Define measurable acceptance for capacity, read path, and failure handling; choose the option in the issue before implementation.

## Scope

The `trajectory_payloads` model, migrations, read and write repositories, acquisition replay and local-attribution read paths, and configuration in `apps/api`; `deploy`, `.env.example`, and `docs`; the object-storage adapter and tests; flow and design documents under this milestone. Each issue's `scope` sets the files it may touch.

## Acceptance

- Payload bytes in the primary database drop significantly, and capacity stops growing linearly with low-frequency historical payloads.
- Compression, object-storage reads, missing objects, and hash mismatches all have repeatable verification; normalized results match the pre-change baseline.
- Migration and rollback are executable; production capacity, read latency, and failure rates are observable.
- The option decision lands in the issue, and the implementation PR follows it.

## Non-goals

Do not change normalization or business-table semantics or existing APIs; do not make upstream re-download the only storage; do not delete historical payloads that lack a durable copy; do not change the upstream trace contract; do not make unrelated UI or product changes.
