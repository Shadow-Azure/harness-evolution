# 对照评测与采纳判定

[English](m3-02-comparative-eval.en.md) | 中文

```yaml flow
kind: issue
milestone: m3
priority: P1
status: backlog
scope:
  - research/**
  - apps/server/src/analysis/**
  - docs/charter.*
  - docs/metrics.*
  - .agents/notes/**
adr: []
github:
  number: 7
  url: https://github.com/Shadow-Azure/harness-evolution/issues/7
```

## 背景

没有对照评测，改动只能靠感觉。需要固定 baseline、任务集与随机种子，按预设阈值判定采纳或拒绝。

## 目标

- 运行 baseline 与 treatment 并记录完整指标。
- 按主指标与护栏指标自动给出判定建议。
- 采纳后更新基线，拒绝时保留复现信息。

## 验收

- 实验记录满足 charter 与 metrics 的全部字段。
- 判定不依赖事后修改阈值。
- 采纳或拒绝都有可执行回滚说明。
