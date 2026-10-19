# 轨迹诊断

[English](m2-diagnosis.en.md) | 中文

```yaml flow
kind: milestone
id: m2
title: 轨迹诊断
status: planned
github:
  number: null
  url: null
```

## 目标

用规则和 AI 识别轨迹中的目标偏移、工具失败、重复重试、未验证修改与错误未闭环，并让每条问题回链到证据。

## 验收

- 规则诊断能产出结构化问题与证据位置。
- AI 诊断使用共享契约输出问题、证据与改进建议。
- 前端问题列表点击证据可跳转到对应轨迹。

## Issues

- [规则诊断与证据定位](../issues/m2-01-rule-diagnosis.md)
- [AI 诊断与结构化输出](../issues/m2-02-ai-diagnosis.md)
