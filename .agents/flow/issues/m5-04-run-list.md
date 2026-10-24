# m5-04 run list

[English](m5-04-run-list.en.md) | 中文

```yaml flow
kind: issue
id: m5-04
milestone: m5
depends:
  - m5-01
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
  number: 53
  url: https://github.com/Shadow-Azure/harness-evolution/issues/53
```

## 背景

m5-04 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m5-04 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [05 §3.5/§4.10 运行模型](../../../plans/fullstack-design/05-api-design.md)
- [08 §8 列表](../../../plans/fullstack-design/08-frontend-implementation.md)
- [02 F10](../../../plans/fullstack-design/README.md)

## 实现内容

- 实现 running/history API 与列表 UI，展示阶段、进度、状态、创建人和时间
- 支持刷新和空态

## 实施步骤

1. 写状态分组和后端文案失败测试
2. 实现 API/页面
3. 用 fixture 驱动 E2E

## 依赖与交付边界

- 依赖：m5-01
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m5-04-run-list
pnpm test:db
pnpm test:web
pnpm test:e2e
pnpm contract:check
```

- 列表测试通过
- running/history 顺序和进度来自后端

## 验收标准

- 不从前端推算状态

## 门禁与 CI

- route gate、组件测试、E2E

## 非目标

- 不做运行详情
