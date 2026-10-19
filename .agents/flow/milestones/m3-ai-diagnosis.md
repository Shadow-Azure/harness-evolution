# M3 AI 轨迹诊断：跨 Agent 证据回链

[English](m3-ai-diagnosis.en.md) | 中文

```yaml flow
kind: milestone
id: m3
title: M3 AI 轨迹诊断：跨 Agent 证据回链
status: planned
github:
  number: 7
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/7
```

## 目标

让主会话分析覆盖全部后代 subagent，并给出可验证、可跳转的问题结论。

## 范围

- 规则诊断与 AI 诊断统一以 session family 为分析范围
- 逐 agent 提炼候选问题，再由主 agent 合并、去重并形成跨 agent 结论
- 分析任务状态、历史、结构化输出与证据校验
- 问题区分 agent 编排、skill 使用、工具执行、验证闭环和成本异常

## 验收

- 主会话的一次分析包含全部后代 subagent
- 每条问题标注作用域、agent 路径、证据与改进建议
- 跨 agent 重复问题只保留一条主问题，并列出相关 agent
- 证据锚点包含 rollout、行号、item/call id，点击可准确跳转
- 大工具输出与图片不会原样送入模型上下文

## 非目标

- 自动修改 skill 或 agent
- 自动合并、发布或权限变更
