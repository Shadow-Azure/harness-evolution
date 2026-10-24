# m2-06 session query api

[English](m2-06-session-query-api.en.md) | 中文

```yaml flow
kind: issue
id: m2-06
milestone: m2
depends:
  - m2-05
priority: P0
status: backlog
scope:
  - apps/api/**
  - packages/contracts/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr:
adr: []
github:
  number: 38
  url: https://github.com/Shadow-Azure/harness-evolution/issues/38
```

## 背景

m2-06 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m2-06 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [05 §3.1/§4.2–4.4 会话 API](../../../plans/fullstack-design/05-api-design.md)
- [06 §7 数据口径](../../../plans/fullstack-design/06-database-design.md)
- [08 §2 前端数据层](../../../plans/fullstack-design/08-frontend-implementation.md)

## 实现内容

- 实现 session list、overview、agent tree 查询
- 支持搜索、状态、时间、密度排序和分页
- 统计读聚合列，问题数当前恒为 0

## 实施步骤

1. 用 seed fixture 写路由/分页/排序/空态失败测试
2. 实现 sessions service
3. 生成 OpenAPI 契约

## 依赖与交付边界

- 依赖：m2-05
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m2-06-session-query-api
pnpm test:db
pnpm contract:check
```

- 会话 API 测试通过
- contract:check 无漂移
- 固定 fixture 的列表聚合可精确断言

## 验收标准

- API 契约与数据库口径一致
- 深链字段齐全

## 门禁与 CI

- API route gate、contract gate、双方言查询测试

## 非目标

- 不返回时间线端点
