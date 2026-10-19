# 轨迹可查看

[English](m1-trace-viewer.en.md) | 中文

```yaml flow
kind: milestone
id: m1
title: 轨迹可查看
status: planned
github:
  number: null
  url: null
```

## 目标

从本机 Codex rollout 导入真实 session，按轮次展示消息、推理、工具调用、输出、错误与 token，并支持从时间线定位任意工具调用。

## 验收

- 能扫描并增量导入一个真实 Codex session。
- SQLite schema、repository 与迁移脚本可运行。
- Web 能打开 session 详情并定位任一条工具调用。

## Issues

- [Codex rollout 扫描与增量入库](../issues/m1-01-rollout-ingest.md)
- [Session 列表与轮次时间线](../issues/m1-02-session-timeline.md)
