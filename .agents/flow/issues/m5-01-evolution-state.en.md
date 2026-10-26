# m5-01 Evolution State

English | [中文](m5-01-evolution-state.md)

```yaml flow
kind: issue
id: m5-01
milestone: m5
depends:
  - m4-04
priority: P0
status: in-progress
scope:
  - apps/api/**
  - apps/api/alembic/**
  - fixtures/**
  - plans/**
  - reports/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 50
  url: https://github.com/Shadow-Azure/harness-evolution/issues/50
```

## Background





m5-01 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m5-01 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [07 §5.1 状态机](../../../plans/fullstack-design/07-backend-implementation.md)
- [06 §5.2 evolution_runs](../../../plans/fullstack-design/06-database-design.md)
- [09 R4/R11](../../../plans/fullstack-design/README.md)

## Implementation





- 实现 evolution 表、unit 游标状态机、engine 工厂和按 attribute_type 分半的确定性占位聚类
- cluster-only 只允许 prepare

## Implementation steps





1. 写状态边界、越界 409、未知 engine、stages 契约和同输入同输出的失败测试
2. 实现状态机/工厂/占位算法

## Dependencies and boundary





- 依赖：m4-04
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m5-01-evolution-state
pnpm test:db
```

- evolution 状态测试通过
- 重复聚类结果 hash 一致

## Acceptance





- 非法阶段不可读写
- 占位行为被测试锁定

## Gates and CI





- 状态机 gate、双方言测试、fixture gate

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
