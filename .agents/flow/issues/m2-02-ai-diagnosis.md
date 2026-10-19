# AI 诊断与结构化输出

[English](m2-02-ai-diagnosis.en.md) | 中文

```yaml flow
kind: issue
milestone: m2
priority: P1
status: backlog
scope:
  - apps/server/src/analysis/**
  - packages/contracts/**
  - docs/**
  - .agents/notes/**
adr: []
github:
  number: null
  url: null
```

## 背景

规则覆盖不了目标偏移与验证缺口。需要模型在完整上下文中诊断，同时保持结构化、可回链与可复现。

## 目标

- 定义诊断输入裁剪与证据引用规则。
- 模型输出经 schema 校验后入库。
- 记录模型、参数、耗时与失败重试。

## 验收

- 非法模型输出被拒绝并可重试。
- 每条 AI 问题至少引用一条真实轨迹证据。
- 诊断记录可复现并带预算上限。
