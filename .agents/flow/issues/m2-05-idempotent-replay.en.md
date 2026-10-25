# m2-05 Idempotent Replay

English | [中文](m2-05-idempotent-replay.md)

```yaml flow
kind: issue
id: m2-05
milestone: m2
depends:
  - m2-04
priority: P0
status: in-progress
scope:
  - apps/api/**
  - apps/api/alembic/**
  - fixtures/**
  - scripts/**
  - tests/**
  - package.json
  - plans/**
  - reports/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 37
  url: https://github.com/Shadow-Azure/harness-evolution/issues/37
```

## Background





m2-05 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 以 root 为原子单位重建会话、Agent、触发点和用户轮次，并推进 source 处理游标。
- hash 与 parser version 未变时零写入；升级或内容变化时只重放受影响 root。
- 同批 root 失败互相隔离，payload 始终只读。

## Design authority





- [06 §3.1 source_records](../../../plans/fullstack-design/06-database-design.md)
- [07 §2.2 幂等事务](../../../plans/fullstack-design/07-backend-implementation.md)
- [09 R7 风险](../../../plans/fullstack-design/README.md)

## Implementation





- pending 由 `processed_hash` 与 `parser_version` 判定，hash/版本未变不刷新处理时间。
- canonical 写入按 `agent_events → agents → user_turns → session_families` 删除，再按 stable key 重写。
- `sync_runs` 记录 total/done/imported/skipped/errors，错误只含脱敏身份与稳定 code。
- 本地 CLI 支持首次重放和重复零副作用验证。

## Implementation steps





1. 先写 pending、首次写入、重复跳过、hash/parser 升级、坏行和 root 隔离测试。
2. 实现 replay repository 与 service，统一处理 source 游标。
3. 以 SQLite、MySQL contract 和真实 4 roots / 66 payload 验证。

## Dependencies and boundary





- 依赖：m2-04
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m2-05-idempotent-replay
pnpm test:db
pnpm data:replay:sessions
```

- test:db 与 test:db:mysql 通过
- 首次真实重放导入 66 个 payload；第二次 `imported=0`、`skipped=66`，业务行与游标时间不变。

## Acceptance





- 4 roots / 66 agents / 53 main user turns 与 pure pipeline 一致。
- 结构失败不推进该 root 游标；其他 root 继续完成。
- 重复输入和 parser 升级均保留可审计的 `sync_runs`。

## Gates and CI





- 双方言 repository gate、迁移 gate、幂等测试

## Non-goals

- Do not delete or rewrite external payloads.
- Do not implement scheduling, sync locks, HTTP/SSE triggers, or job progress beyond `processed_*`; those belong to m2-06/m2-07.
