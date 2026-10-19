# Codex rollout 扫描与增量入库

[English](m1-01-rollout-ingest.en.md) | 中文

```yaml flow
kind: issue
milestone: m1
priority: P0
status: backlog
scope:
  - apps/server/src/ingest/**
  - apps/server/src/storage/**
  - packages/contracts/**
  - docs/architecture.*
  - .agents/notes/**
adr: []
github:
  number: null
  url: null
```

## 背景

没有轨迹导入，前端与诊断都没有真实数据源。Codex rollout 是 JSONL，需要可重放的解析与幂等入库。

## 目标

- 扫描本机 Codex session 目录并识别新 rollout。
- 解析原始记录，归一化为 session / turn / item。
- 用 SQLite repository 幂等写入，保留原始记录。

## 验收

- 同一 rollout 重复导入不产生重复数据。
- 解析失败有明确错误与原始行定位。
- 为解析与幂等性提供自动化测试。
