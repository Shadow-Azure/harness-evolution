# Agent 执行流图触发点直连与按需显示

[English](m6-agent-tree-trigger-edges.en.md) | 中文

```yaml flow
kind: issue
id: m6-06
milestone: m6
depends: []
priority: P1
status: in-progress
scope:
  - plans/14-15-ui-prototype/**
  - plans/fullstack-design/**
  - plans/2026-10-28-pr152-review.md
  - apps/web/src/components/agent-tree/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/implemented/bug-fix/2026-10-28-agent-tree-direct-trigger-edges.md
github:
  number: 149
  url: https://github.com/Shadow-Azure/harness-evolution/issues/149
```

## 背景

Agent 执行流图把每个触发 pill 到 Agent 盒边的装饰线作为常驻 stub 渲染，stub 不读取真实边，因此没有子 Agent 或问题卡的 pill 仍显示上下竖线。真实 Vue Flow edge 从 Agent 盒边缘出发，错误详情页还会被节点层遮挡，用户看到的是盒边到目标相连，而不是触发 pill 与目标相连。

## 目标

- 无真实目标的触发 pill 不显示任何上下连线。
- 子 Agent、self-skill 问题卡与 discovery 问题卡都从对应 pill 的精确锚点直接连接。
- 同一 pill 的多个问题卡分别向上或向下形成稳定纵向列，并沿列串联。
- 主执行流与错误详情保持相同连接语义，edge 不被节点背景遮挡。

## 设计依据

- [plans/fullstack-design/03-frontend-architecture.md §8.3](../../../plans/fullstack-design/03-frontend-architecture.md#83-agent-执行流图react-flow--vue-flow-的迁移方案)：Vue Flow handle 与边路径保持原型语义。
- [plans/fullstack-design/08-frontend-implementation.md §3](../../../plans/fullstack-design/08-frontend-implementation.md#3-agent-执行流图componentsagent-tree)：self 与 discovery 问题卡按触发点锚定。
- [plans/14-15-ui-prototype/harness-evolution.html](../../../plans/14-15-ui-prototype/harness-evolution.html)：触发 pill 是真实边的源锚点，问题卡纵向堆叠。
- 实现冲突时以上链接章节和已确认原型为准。

## 实现内容

- 布局阶段根据真实 Agent 边和问题卡首边汇总每个 Agent 的 pill handle 占用。
- Agent 节点只为被占用的方向创建 handle，handle 定位在 pill 的上/下边界。
- 删除常驻 stub；提高 edge 层，避免其被 Agent 节点背景覆盖。
- 问题卡居中于 pill 的 x 坐标；同一锚点的后续卡片沿列堆叠，边从前一张卡片继续到下一张。

## 实施步骤

1. 在布局单测中覆盖无连接 pill、真实连接聚合、上下问题卡堆叠。
2. 在节点单测中覆盖按需 handle、pill 锚点与问题卡堆叠 handle。
3. 扩展布局与节点类型，生成触发连接状态和纵向问题卡边。
4. 调整 AgentTree 画布层级并运行前端、流程与文档门禁。

## 依赖与交付边界

- 依赖：无
- 交付边界：只调整 Agent 执行流图的锚定、连线与堆叠；不改变折叠算法、问题卡交互、数据契约或后端。

## 独立验证

```sh
pnpm --filter @harness/web exec vitest run src/components/agent-tree/layout.test.ts src/components/agent-tree/nodes/AgentNode.test.ts src/components/agent-tree/nodes/BadCaseNode.test.ts
pnpm typecheck:web
pnpm lint:web
```

- 单测覆盖无连接 pill 不生成 handle、真实连接生成 pill 锚点、上下问题卡分别串联；断言全部通过。
- 类型与 lint 无错误。

## 验收标准

- `/agent-tree-demo?variant=large` 中只有存在子 Agent 或问题卡的 pill 显示对应连线。
- 子 Agent 边从 pill 下沿出发；上方错误卡从底边接 pill 上沿；下方错误卡从 pill 下沿接第一张卡。
- 同一 pill 的多个错误卡分别向上或向下形成一列，后一张卡串联前一张。
- 错误详情执行流中上述边完整可见，节点文字、点击和缩放控件不受影响。

## 门禁与 CI

- `pnpm test:web`
- `pnpm typecheck:web`
- `pnpm lint:web`
- `pnpm verify:flow`
- `pnpm lint:docs` / `pnpm verify:docs`
- `pnpm verify:web-style`

## 非目标

- 不改变 React Flow 到 Vue Flow 的布局架构和现有折叠阈值。
- 不调整问题卡左右侧判定、卡片内容或深链行为。
- 不修改 API、数据库或共享契约。
