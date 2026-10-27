# m5-06 Six Step Api

English | [中文](m5-06-six-step-api.md)

```yaml flow
kind: issue
id: m5-06
milestone: m5
depends:
  - m5-01
priority: P0
status: in-progress
scope:
  - apps/api/**
  - packages/contracts/**
  - fixtures/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 55
  url: https://github.com/Shadow-Azure/harness-evolution/issues/55
```

## Background





m5-06 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m5-06 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [05 §3.6 六步产出](../../../plans/fullstack-design/05-api-design.md)
- [07 §5.10](../../../plans/fullstack-design/07-backend-implementation.md)
- [09 R4](../../../plans/fullstack-design/README.md)

## Implementation





- 实现筛选/聚类/归因/排序/迭代/终评六个只读端点
- 后端直出 status/clickable
- 未到达 404

## Implementation steps





1. 按 05 §3.6 建六组 fixture 与快照测试
2. 实现 stage service
3. 验证 preparing/blocked

## Dependencies and boundary





- 依赖：m5-01
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m5-06-six-step-api
pnpm test:db
pnpm contract:check
```

- 六步 API 测试通过
- OpenAPI 快照稳定
- 不可读步骤 404

## Acceptance





- 状态判断只在后端

## Gates and CI





- contract gate、route tests、state gate

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
