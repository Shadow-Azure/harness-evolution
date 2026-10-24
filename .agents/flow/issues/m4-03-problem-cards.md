# m4-03 problem cards

[English](m4-03-problem-cards.en.md) | 中文

```yaml flow
kind: issue
id: m4-03
milestone: m4
depends:
  - m4-02
priority: P0
status: backlog
scope:
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 48
  url: https://github.com/Shadow-Azure/harness-evolution/issues/48
```

## 背景

m4-03 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m4-03 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [03 §8.3 问题卡](../../../plans/fullstack-design/03-frontend-architecture.md)
- [08 §3.4 联动](../../../plans/fullstack-design/08-frontend-implementation.md)
- [09 追溯矩阵](../../../plans/fullstack-design/README.md)

## 实现内容

- 在执行流节点渲染问题卡、状态色、数量与锚点
- 问题列表与画布双向定位
- 点击节点/卡片高亮证据

## 实施步骤

1. 用五态 fixture 写图卡与联动失败测试
2. 实现组件与状态
3. 验证本地会话定位

## 依赖与交付边界

- 依赖：m4-02
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m4-03-problem-cards
pnpm test:db
pnpm test:web
pnpm test:e2e
```

- 列表点击画布定位正确
- 卡片状态色与常量表一致

## 验收标准

- 问题可视化可回链 badCaseId

## 门禁与 CI

- 组件测试、E2E、视觉状态断言

## 非目标

- 不修改归因算法
