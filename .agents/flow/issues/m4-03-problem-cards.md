# m4-03 problem cards

[English](m4-03-problem-cards.en.md) | 中文

```yaml flow
kind: issue
id: m4-03
milestone: m4
depends:
  - m4-02
priority: P0
status: in-progress
scope:
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - tests/**
  - plans/**
  - reports/**
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

- 读取 Session 的五态问题详情，并在执行流图按 `anchor.agentId + anchor.eventIndex` 渲染问题卡。
- `self + agent`、`self + skill`、`discovery` 与 `eventIndex=-1` 分别使用侧向、触发、发现和 fallback 语义连线；无效宿主只保留卡片，不产生孤儿边。
- 问题卡按文本实测宽度落在 150–400px，同宿主不同锚点也按最终矩形稳定避碰；折叠宿主在展开前不生成浮卡。
- 问题列表展示真实 ID、五态、归因摘要、上报对象与 metadata facts；画布卡保持原型结构性红色。
- 列表和画布共享一个活动 `badCaseId`，双向定位与高亮；列表选择先展开折叠祖先，画布定位完成后滚动列表，并取消迟到的初始滚动重置。
- 问题详情加载、失败、重试与空态独立于 Session 概要与执行流。

## 实施步骤

1. 用五态 fixture 写图卡、锚点、坏锚点与双向联动失败测试。
2. 实现问题卡、语义连线、五态列表与独立查询。
3. 用四个真实 fixture Session 与折叠树覆盖五态、桌面/移动布局和定位恢复。

## 依赖与交付边界

- 依赖：m4-02
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:web
pnpm test:e2e -- "m4 problem cards"
pnpm typecheck:web
pnpm lint:web
```

- 四个 fixture Session 合计呈现未分析、非问题、模型、prompt 与错误五态。
- 列表点击定位并高亮画布卡；画布卡点击滚动并高亮对应列表行。
- 1408px 与 390px 无横向溢出，浏览器 console 无错误。

## 验收标准

- 问题可视化可回链 badCaseId

## 门禁与 CI

- 组件测试、布局纯函数测试、真实 Chrome E2E、TypeScript、ESLint、token 色源与 bundle 边界。

## 非目标

- 不修改归因算法
- 不实现 m4-04 的错误详情与归因双 Tab
