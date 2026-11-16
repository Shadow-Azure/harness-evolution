# M9 Session 证据与对象版本

[English](m9-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m9
title: M9 Session 证据与对象版本
status: done
github:
  number: 19
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/19
```

## 目标

建立可扩展的多 Agent 轨迹解析边界，并把真实轨迹中的 runtime、关系、完成度、对象 revision、定义指纹与 Skill、Agent、知识库触发点变成稳定证据。

## 范围

runtime 身份与 parser 工厂、元数据兼容、关系置信度、执行完成状态、触发坐标、对象 revision、agent/skill 定义指纹、文件读取证据、知识库文档触发与重放。

## 验收

脱敏的 Claude Code 主/子会话金样可重建关系、完成度、Skill body 与 agent prompt 证据；新增 runtime 只注册 parser 子类；未知版本和未知 runtime 不会被误报为精确命中。

## 非目标

不实现潜在匹配、归因引擎、七步 run 或多 runtime 的前端展示。
