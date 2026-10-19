# 规则诊断与证据定位

[English](m2-01-rule-diagnosis.en.md) | 中文

```yaml flow
kind: issue
milestone: m2
priority: P0
status: backlog
scope:
  - apps/server/src/analysis/**
  - packages/contracts/**
  - docs/architecture.*
  - .agents/notes/**
adr: []
github:
  number: 4
  url: https://github.com/Shadow-Azure/harness-evolution/issues/4
```

## 背景

人工逐轮读轨迹成本高。先把可机械识别的问题做成规则：工具失败、重复重试、未验证修改、错误未闭环。

## 目标

- 定义问题、证据与严重度的共享契约。
- 实现规则诊断并持久化分析任务。
- 每条问题携带可跳转的证据位置。

## 验收

- 对固定夹具轨迹产出稳定问题列表。
- 规则命中与漏报有测试覆盖。
- 诊断结果可通过 API 读取。
