# Turn 时间线核心渲染

[English](m1-timeline-core.en.md) | 中文

```yaml flow
kind: issue
milestone: m1
priority: P0
status: backlog
scope:
  - apps/web/src/**
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 15
  url: https://github.com/Shadow-Azure/harness-evolution/issues/15
```

## 背景

复杂 session 混合用户消息、推理、Agent 消息、命令、文件变更、MCP、子 agent 活动与错误。用户需要沿 turn 读懂主任务，而不是面对一长串无结构事件。

## 目标

- 按 turn 分组渲染时间线。
- 为用户、Agent、推理、工具调用、工具输出、文件变更、错误与 token 提供专门卡片。
- 用 call_id 配对工具调用与输出。
- 支持长文本折叠、复制与原始载荷查看。

## 验收

- 能完整浏览 root session 的全部 turn 和事件。
- 工具调用与输出不会错配，失败状态与退出码可见。
- 用户消息与 Agent 最终回复在长轨迹中容易定位。
- 长输出默认折叠，可展开查看原始内容。
- turn 边界、时间与耗时信息保持一致。
