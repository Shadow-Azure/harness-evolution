# 工程与流程基线

[English](m0-docs-gates.en.md) | 中文

```yaml flow
kind: milestone
id: m0
title: 工程与流程基线
status: done
github:
  number: null
  url: null
```

## 目标

打通 pnpm workspace、前后端骨架与健康检查，并把文档工程、PR 检视与 roadmap → milestone → issue 门禁落地。

## 验收

- `pnpm build`、`pnpm typecheck` 与健康检查可用。
- 文档分层、双语配对、Agent Notes 与流程树齐备。
- `pnpm verify:docs` 与 `pnpm verify:flow` 全绿并接入 CI。

## Issues

- [文档、检视与流程门禁体系](../issues/m0-01-docs-gate-system.md)
