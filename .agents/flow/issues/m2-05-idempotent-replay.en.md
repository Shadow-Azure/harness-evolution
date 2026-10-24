# m2-05 Idempotent Replay

English | [中文](m2-05-idempotent-replay.md)

```yaml flow
kind: issue
id: m2-05
milestone: m2
depends:
  - m2-04
priority: P0
status: backlog
scope:
  - apps/api/**
  - apps/api/alembic/**
  - fixtures/**
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





- 完成 m2-05 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [06 §3.1 source_records](../../../plans/fullstack-design/06-database-design.md)
- [07 §2.2 幂等事务](../../../plans/fullstack-design/07-backend-implementation.md)
- [09 R7 风险](../../../plans/fullstack-design/README.md)

## Implementation





- 实现 source_records、content hash、parser_version 和事务内先删后写
- 重复 payload 零重复
- 同一批内单条失败可隔离重放

## Implementation steps





1. 写双方言重复导入、升级重放、坏行重放的失败测试
2. 实现 replay service
3. 验证 sqlite 与 mysql 行数一致

## Dependencies and boundary





- 依赖：m2-04
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m2-05-idempotent-replay
pnpm test:db
```

- test:db 与 test:db:mysql 通过
- 重复导入 count/source_records/hash 不变

## Acceptance





- 幂等指标无 diff
- 升级后可重放并保留审计

## Gates and CI





- 双方言 repository gate、迁移 gate、幂等测试

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
