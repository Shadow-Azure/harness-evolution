# M4 自进化闭环：Skill 与 Agent 改进评测

[English](m4-evolution-loop.en.md) | 中文

```yaml flow
kind: milestone
id: m4
title: M4 自进化闭环：Skill 与 Agent 改进评测
status: planned
github:
  number: 8
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/8
```

## 目标

把真实问题转化为有证据、可回滚的 harness 改进。

## 范围

- 按 skill 或 agent 聚合已归因问题
- 生成最小改动提案并绑定原始证据
- 对照评测、护栏指标与采纳/回滚记录

## 验收

- 至少一条真实问题完成“诊断 → 提案 → 对照验证 → 采纳或拒绝”
- 自进化入口必须先选择目标 skill 或 agent，并展示其问题集合
- 提案可追溯到问题、session family 与具体证据
- 采纳和回滚都有版本标识与评测结果

## 非目标

- 模型权重训练
- 无评测证据的自动合并
