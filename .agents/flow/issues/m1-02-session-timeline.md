# Session 列表与轮次时间线

[English](m1-02-session-timeline.en.md) | 中文

```yaml flow
kind: issue
milestone: m1
priority: P1
status: backlog
scope:
  - apps/web/**
  - apps/server/src/sessions/**
  - packages/contracts/**
  - docs/architecture.*
  - .agents/notes/**
adr: []
github:
  number: null
  url: null
```

## 背景

导入后的轨迹需要可读界面：按轮次展示目标、消息、推理、工具调用、输出、错误与 token，并能定位到任意一条工具调用。

## 目标

- 提供 session 列表与详情 API。
- 前端按轮次渲染时间线，支持展开与定位。
- 空状态、加载失败与大 session 有明确处置。

## 验收

- 能在前端打开一个真实 Codex session。
- 点击任一工具调用可看到完整输入输出与错误。
- 列表与详情的字段来自共享契约。
