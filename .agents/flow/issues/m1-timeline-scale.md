# 长轨迹虚拟化与大载荷降级

[English](m1-timeline-scale.en.md) | 中文

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
  number: 16
  url: https://github.com/Shadow-Azure/harness-evolution/issues/16
```

## 背景

选定的 4 个家族有 25,170 条记录与 72.2MB 原始载荷，单文件最大超过 20MB，单条工具输出接近 800KB。一次渲染全部事件会让原型失去可操作性。

## 目标

- 按 turn 懒加载并虚拟化长列表。
- 对大工具输出、MCP 结果与图片提供摘要和按需展开。
- 避免把原始 JSONL 或整份 fixture 打进前端首包。
- 保留滚动位置、选中 agent 与证据定位。

## 验收

- 打开 25,170 条记录的家族时首屏可交互，不等待全部事件渲染。
- 3,000 条以上的 root session 可以连续滚动并按 turn 分段。
- 大工具输出默认只显示摘要，展开后才读取完整文本。
- 图片显示路径与缩略占位，不阻塞时间线。
- 跳转到证据后滚动位置稳定，不触发全量重排。
