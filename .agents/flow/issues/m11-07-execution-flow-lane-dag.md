# 执行流 lane DAG 与结构树切换

[English](m11-07-execution-flow-lane-dag.en.md) | 中文

```yaml flow
kind: issue
id: m11-07
milestone: m11
depends:
  - m8-05
  - m9-04
priority: P1
status: ready
scope:
  - apps/web/src/components/agent-tree/**
  - apps/web/src/components.d.ts
  - apps/web/src/pages/agent-tree-demo/**
  - apps/web/src/pages/sessions/**
  - apps/web/src/pages/errors/**
  - tests/e2e/**
  - plans/fullstack-design/**
  - plans/*-review.md
  - plans/ui-prototype-v2/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 276
  url: https://github.com/Shadow-Azure/harness-evolution/issues/276
```

## 背景

V2 原型已经把 Session 和错误详情的默认执行流改为小窗口 lane DAG：一条 lane 表示一次 agent invocation，bar 的左右边界对应日志行区间，跨 lane 重叠表示并发，嵌套用 `A1/A1.1` 深度表达，选中 bad case 时保留全部并发分支并高亮对应 BC。原型的结构树仍保留为切换视图。

但 02/03/08/09 仍描述 Vue Flow 节点树、`×N` message 间隔、`>8` 子 agent 折叠和“选中时只留该问题卡”。M11-02 的交付边界又明确写“不改执行流图布局”，因此 M7–M12 没有任何 issue 承接这一目标态。

## 目标

- 默认渲染小窗口 lane DAG，支持 `A1/A1.1` 深度、日志行区间 bar、跨 lane 并发和 BC marker。
- 所有 lane 展开，不再按 `>8` 折叠；用视口缩放和平移替代折叠。
- 保留结构树切换视图；两种视图共享同一选中 case 和深链。
- 选中 bad case 时保留全部并发分支，只高亮对应 BC 和定位线，不过滤掉其他分支。
- 移除 V2 执行流中残留的时间线入口和 `打开时间线` CTA。

## 设计依据

- [02 §2.1 Session 错误查看域](../../../plans/fullstack-design/02-features.md#21-session-错误查看域)：执行流与错误详情的功能口径。
- [08 §3 Agent 执行流图](../../../plans/fullstack-design/08-frontend-implementation.md#3-agent-执行流图componentsagent-tree)：lane DAG、结构树和选中态实现。
- [09 §1.2 Session 错误查看](../../../plans/fullstack-design/09-review-guide.md#12-session-错误查看)：评审清单。
- [design-v2 §8 错误详情](../../../plans/ui-prototype-v2/design-v2.md#8-错误详情一个-bad-case--多条归因)：原型交互。

## 实现内容

- 新增 `LaneDag` 视图：虚拟画布、固定高度视口、滚轮缩放、拖拽平移、适应/1:1、双指/触摸平移。
- 用 `A1/A1.1` 路径和缩进表达深度，用跨 lane 横向重叠表达并发；同 lane bar 保持不重叠。
- 主链 `×N 无触发` 条继续按日志行区间表达；不再生成 `×N` message 间隔节点。
- 保留 `AgentTree` 结构树作为切换视图；DAG 和树共享 `badCaseId` 选中态和 `locate`。
- 选中 case 时 DAG 保留全部分支并高亮 BC 定位线；错误详情不再过滤整棵执行流。
- 删除 V2 页面里的时间线 tab、页面和 `打开时间线` 按钮，只保留 Session / 错误详情入口。

## 实施步骤

1. 先把现有结构树和 DAG 的数据适配抽成共享 `laneModel`，补深度/并发/区间单测。
2. 实现小窗口、zoom/pan/fit，并保留结构树切换。
3. 接入 Session 与错误详情的选中 case、定位和深链。
4. 删除时间线入口与页面，更新 E2E 和视觉回归。
5. 更新 02/03/08/09/15 与 design-v2，补齐评审清单。

## 依赖与交付边界

- 依赖：m8-05、m9-04
- 非目标：不改后端 tree 契约；不实现多归因左栏（M11-02）；不实现 parser/证据（M9）。

## 独立验证

```sh
pnpm test:web
pnpm typecheck:web
pnpm test:e2e -- --pattern execution-flow
pnpm verify:bundle
```

- Session 和错误详情默认显示 lane DAG，无同 lane bar 重叠。
- 跨 lane 重叠可见，选中 case 保留全部分支并高亮。
- 结构树切换后选中态和深链不丢失。
- 56 个 subagent 会话可缩放浏览，不出现 `>8` 折叠节点。
- 页面不再出现时间线入口。

## 验收标准

- 默认视图、选中态、深链和结构树切换与 V2 原型一致。
- 所有 lane 展开，通过视口缩放/平移浏览，而不是折叠。
- 同一 case 的选中态在 DAG、结构树和问题列表之间一致。
- 无控制台错误、明显裁切/重叠或布局跳动。

## 门禁与 CI

- Web 单测、类型、E2E、bundle、视觉回归与 flow 门禁。

## 非目标

- 不把执行流改回 React Flow/Vue Flow 节点树作为默认视图。
- 不保留时间线页面或 `打开时间线` CTA。
- 不以过滤分支的方式表达选中 case。
