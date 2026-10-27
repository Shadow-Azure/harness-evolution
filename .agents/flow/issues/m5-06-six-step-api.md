# m5-06 six step api

[English](m5-06-six-step-api.en.md) | 中文

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

## 背景

m5-06 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m5-06 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [05 §3.6 六步产出](../../../plans/fullstack-design/05-api-design.md)
- [07 §5.10](../../../plans/fullstack-design/07-backend-implementation.md)
- [09 R4](../../../plans/fullstack-design/README.md)

## 实现内容

- 实现筛选/聚类/归因/排序/迭代/终评六个只读端点
- 后端直出 status/clickable
- 未到达 404

## 实施步骤

1. 按 05 §3.6 建六组 fixture 与快照测试
2. 实现 stage service
3. 验证 preparing/blocked

## 依赖与交付边界

- 依赖：m5-01
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m5-06-six-step-api
pnpm test:db
pnpm contract:check
```

- 六步 API 测试通过
- OpenAPI 快照稳定
- 不可读步骤 404

## 验收标准

- 状态判断只在后端

## 门禁与 CI

- contract gate、route tests、state gate

## 非目标

- 不实现前端
