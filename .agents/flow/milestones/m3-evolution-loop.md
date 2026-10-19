# 自进化闭环

[English](m3-evolution-loop.en.md) | 中文

```yaml flow
kind: milestone
id: m3
title: 自进化闭环
status: planned
github:
  number: 4
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/4
```

## 目标

把诊断问题归因到 skill / prompt / 工具 / 控制流，生成最小改动提案，并用对照评测决定采纳或回滚。

## 验收

- 至少一条真实问题走完"诊断 → 提案 → 对照验证 → 采纳或拒绝"。
- 实验记录包含 baseline、treatment、指标、预算与决策规则。
- 采纳或拒绝可由版本或开关回滚。

## Issues

- [改进提案生成与归因](../issues/m3-01-improvement-proposal.md)
- [对照评测与采纳判定](../issues/m3-02-comparative-eval.md)
