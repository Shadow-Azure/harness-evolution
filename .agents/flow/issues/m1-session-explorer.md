# Session 浏览器与家族摘要

[English](m1-session-explorer.en.md) | 中文

```yaml flow
kind: issue
milestone: m1
priority: P0
status: backlog
scope:
  - apps/web/src/**
  - apps/web/package.json
  - pnpm-lock.yaml
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 14
  url: https://github.com/Shadow-Azure/harness-evolution/issues/14
```

## 背景

原型需要先让用户看到 4 个复杂 session 的家族规模、任务状态和问题密度。顶层列表只展示 root session，子 agent 留在详情页，避免把协作轨迹误当成独立对话。

## 目标

- 建立左侧 Session 浏览器与家族摘要卡。
- 展示 turn、agent、command、failure、skill 与 finding 聚合数量。
- 支持按仓库、时间、状态和问题密度筛选。
- 用 URL 保存当前 root session、选中 agent 与证据位置。

## 验收

- 顶层只出现 4 个 root session，并显示其后代 agent 数。
- 每个摘要能区分 20:05、17:32、08:46 与 12:34 四类复杂场景。
- 搜索和筛选能在一屏内定位目标 session。
- 刷新页面后恢复 root session、agent 与证据位置。
- 空列表、未选中 session 与加载失败都有明确状态。
