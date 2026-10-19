# 家族级问题面板与证据跳转

[English](m1-findings-panel.en.md) | 中文

```yaml flow
kind: issue
milestone: m1
priority: P0
status: backlog
scope:
  - apps/web/src/**
  - packages/contracts/**
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 12
  url: https://github.com/Shadow-Azure/harness-evolution/issues/12
```

## 背景

原型的核心是让用户看到“这个 session 出了什么问题”。主 agent 与全部 subagent 的问题必须统一出现在同一个列表里，用户无需逐个切换 agent 才能了解全貌；原型阶段使用人工核对的诊断快照，并明确标注不是实时 AI 结果。

## 目标

- 在右侧用单一列表展示主 agent 与全部子 agent 的问题。
- 每条问题标注来源 agent，并可按 agent 过滤，但过滤不拆分数据源。
- 支持严重度、类别与 agent 筛选。
- 每条问题包含结论、证据与改进建议。
- 选中问题后打开归因详情，并能继续进入自进化模拟。
- 点击证据后定位到对应 rollout、agent、turn 与事件并高亮。

## 验收

- 4 个 root session 各有可演示的诊断快照。
- 初始视图同时包含主 agent 与子 agent 的问题，无需切换来源。
- 每条问题都有来源 agent 标签，并可按 agent 筛选。
- 跨 agent 问题只出现一次，并能展开相关子 agent 证据。
- 任一子 agent 的示例问题都能从流程图或问题面板打开。
- 问题面板能区分 agent 编排、skill 使用、工具失败与验证缺口。
- 每条问题都能打开对应归因详情，不出现断开的演示路径。
- 证据跳转在长轨迹中仍然准确。
- 页面明确标注“示例诊断快照”，不冒充实时模型分析。
