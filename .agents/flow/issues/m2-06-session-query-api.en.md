# m2-06 Session Query Api

English | [中文](m2-06-session-query-api.md)

```yaml flow
kind: issue
id: m2-06
milestone: m2
depends:
  - m2-05
priority: P0
status: in-progress
scope:
  - apps/api/**
  - packages/contracts/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
  - reports/**
adr: []
github:
  number: 38
  url: https://github.com/Shadow-Azure/harness-evolution/issues/38
```

## Background





m2-06 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m2-06 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [05 §3.1/§4.2–4.4 会话 API](../../../plans/fullstack-design/05-api-design.md)
- [06 §7 数据口径](../../../plans/fullstack-design/06-database-design.md)
- [08 §2 前端数据层](../../../plans/fullstack-design/08-frontend-implementation.md)

## Implementation





- Implement session list, overview, and flat Agent-tree queries.
- Search titles/repositories, filter status, sort stably, and apply a limit.
- Read canonical aggregate columns; aggregate issue counts from the read-only external table for the current page.
- Return event offsets, stable labels, parent/tool-use edges, and bad-case anchors.

## Implementation steps





1. Add failing route, search, sort, empty-state, and authentication tests from seeded fixtures.
2. Implement the sessions repository/service and read-only API.
3. Generate OpenAPI contracts and verify SQLite/MySQL query semantics.

## Dependencies and boundary





- 依赖：m2-05
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m2-06-session-query-api
pnpm test:db
pnpm contract:check
```

- 会话 API 测试通过
- contract:check 无漂移
- 固定 fixture 的列表聚合可精确断言
- MySQL session-query contracts pass.

## Acceptance





- API 契约与数据库口径一致
- 深链字段齐全
- The retired timeline endpoint remains unavailable.

## Gates and CI





- API route gate、contract gate、双方言查询测试

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
