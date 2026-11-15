# M9 Session 证据与对象版本

[English](m9-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m9
title: M9 Session 证据与对象版本
status: planned
github:
  number: 19
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/19
```

## 目标

把真实轨迹中的关系、完成度、对象 revision 与 Skill、Agent、知识库触发点变成稳定证据。

## 范围

元数据兼容、关系置信度、执行完成状态、触发坐标、revision 解析、知识库文档触发与重放。

## 验收

脱敏 ccbdb2f0 金样的根因证据可重建；未知版本不会被误报为精确命中。

## 非目标

不实现潜在匹配、归因引擎或七步 run。
