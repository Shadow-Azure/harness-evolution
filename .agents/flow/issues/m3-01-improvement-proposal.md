# 改进提案生成与归因

[English](m3-01-improvement-proposal.en.md) | 中文

```yaml flow
kind: issue
milestone: m3
priority: P0
status: backlog
scope:
  - apps/server/src/analysis/**
  - packages/contracts/**
  - research/**
  - docs/charter.*
  - docs/metrics.*
  - .agents/notes/**
adr: []
github:
  number: null
  url: null
```

## 背景

诊断问题只有转成最小改动才有价值。提案必须说明归因层级、预期影响与回滚方式。

## 目标

- 把问题归因到 skill / prompt / 工具 / 控制流。
- 生成最小改动提案与验证计划。
- 提案引用 baseline、任务集与决策规则。

## 验收

- 至少一条真实问题生成可评审提案。
- 提案包含约束、候选、选型理由与回滚方式。
- 提案不改动评测器与 harness 同一变量。
