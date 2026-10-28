# Agent Note: Agent 执行流图的触发点直连

Status: implemented

[English](2026-10-28-agent-tree-direct-trigger-edges.en.md) | 中文

## Problem

Agent 执行流图中，触发 pill 与目标之间的视觉线由节点内常驻 stub 和从 Agent 盒边出发的 Vue Flow edge 两段拼成。stub 不读取真实边，因而没有目标的 pill 也显示线条；错误详情页的节点层还会遮住真实 edge。用户无法从图上区分触发点是否真的连接了子 Agent 或问题卡，也看不出连接从哪个 pill 发出。

## Decision

布局阶段把真实 Agent 边和问题卡首边的 `h{eventIndex}` / `rep{eventIndex}` 汇总为 `triggerConnections`。Agent 节点只为被占用的方向创建精确位于 pill 上沿或下沿的 handle；不再渲染 stub。edge 层位于节点背景之上，但保持 pointer events 关闭。问题卡以 pill 的 x 坐标居中，同一 pill 的后续卡片沿同一列堆叠，并从上一张卡片的同向 handle 串联到下一张。

## Alternatives considered

保留 stub 并仅在存在边时显示，能以较小改动消除悬空线，但仍需要维护节点内 stub 与盒外 edge 的两套几何，接缝和层级问题会继续存在。把 pill 到盒边的线段烘焙进每条自定义 edge 路径也可实现直连，却要求 edge 感知节点内部布局，扩大折叠、缩放和问题卡组合的回归面。让多个问题卡分别直连同一个 pill 会形成重叠线束，阅读成本高于纵向串联，因此未采用。

## Consequences

触发点是否连线完全由布局数据决定，新增连接类型必须在布局阶段占用对应 handle。问题卡纵向堆叠会增加画布高度，但能保持每个 pill 独立成列。Vue Flow edge 覆盖节点背景后，若未来新增节点内装饰层，需要继续遵守 edge 不接收指针事件与节点内容可交互的边界。
