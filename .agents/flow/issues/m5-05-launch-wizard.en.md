# m5-05 Launch Wizard

English | [中文](m5-05-launch-wizard.md)

```yaml flow
kind: issue
id: m5-05
milestone: m5
depends:
  - m5-02
  - m5-04
priority: P0
status: backlog
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 54
  url: https://github.com/Shadow-Azure/harness-evolution/issues/54
```

## Background





m5-05 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m5-05 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [05 §4.9/§4.10 启动](../../../plans/fullstack-design/05-api-design.md)
- [08 §9 向导](../../../plans/fullstack-design/08-frontend-implementation.md)
- [07 §5.3](../../../plans/fullstack-design/07-backend-implementation.md)

## Implementation





- 实现 probe 命中预览、两步向导、202+runId 和 cluster_only run
- 禁用未配置对象

## Implementation steps





1. 写命中统计、无效配置、仅聚类状态失败测试
2. 实现预览 API 与向导
3. E2E 启动 cluster-only

## Dependencies and boundary





- 依赖：m5-02, m5-04
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m5-05-launch-wizard
pnpm test:db
pnpm test:web
pnpm test:e2e
pnpm contract:check
```

- 向导可完成并跳详情
- cluster_only 只允许 preparing/cluster 结果

## Acceptance





- 启动参数与命中结果可追溯

## Gates and CI





- route gate、E2E、状态机测试

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
