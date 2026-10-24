# m4-01 External Read Models

English | [中文](m4-01-external-read-models.md)

```yaml flow
kind: issue
id: m4-01
milestone: m4
depends:
  - m3-05
priority: P0
status: backlog
scope:
  - apps/api/**
  - apps/api/alembic/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr:
adr: []
github:
  number: 46
  url: https://github.com/Shadow-Azure/harness-evolution/issues/46
```

## Background





m4-01 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m4-01 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [06 §4 外部只读表](../../../plans/fullstack-design/06-database-design.md)
- [05 §3.4 问题模型](../../../plans/fullstack-design/05-api-design.md)
- [09 R2 风险](../../../plans/fullstack-design/README.md)

## Implementation





- 创建 bad_cases/analysis/probe_reports 只读映射与五态 fixtures
- 实现缺失字段降级、防御校验和只读约束

## Implementation steps





1. 写五态、缺失字段、不一致状态的失败测试
2. 实现只读 repository
3. 确保 Alembic 不写外部表

## Dependencies and boundary





- 依赖：m3-05
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m4-01-external-read-models
pnpm test:db
```

- 双方言查询通过
- 五态与降级路径断言完整

## Acceptance





- 外部字段漂移不会崩溃且日志可定位

## Gates and CI





- 双方言 gate、fixture schema gate、只读 lint/测试

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
