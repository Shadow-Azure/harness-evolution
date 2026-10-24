# 原型演示体验与验收收口

[English](m1-prototype-polish.en.md) | 中文

```yaml flow
kind: issue
milestone: m1
priority: P1
status: ready
scope:
  - apps/web/src/**
  - apps/web/index.html
  - .gitignore
  - .agents/flow/issues/m1-prototype-polish*
  - .agents/flow/issues/m1-contracts-snapshot-loader*
  - plans/**
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 13
  url: https://github.com/Shadow-Azure/harness-evolution/issues/13
```

## 背景

原型需要用于真实评审和后续实现对齐。除主流程外，还要处理响应式、键盘操作、状态反馈与演示说明，避免评审时被边缘情况打断。

## 目标

- 完成桌面与窄屏布局，保证三栏信息层级清晰。
- 补齐加载、空数据、解析失败与无诊断结果状态。
- 支持键盘切换 session、agent 与问题证据。
- 提供演示脚本与验收截图。

## 验收

- 1440px 与 1024px 宽度下主流程可用。
- 所有按钮与可交互卡片有 hover、focus 与 disabled 状态。
- 4 个复杂样本按固定路径可逐项演示。
- README 或演示说明列出启动方式、样本范围和已知限制。
- 原型评审无需开发者在旁解释关键交互。
