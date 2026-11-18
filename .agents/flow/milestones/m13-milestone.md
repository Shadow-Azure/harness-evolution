# M13 归因身份与后处理锚点

[English](m13-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m13
title: M13 归因身份与后处理锚点
status: planned
github:
  number: 21
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/21
```

## 目标

让 skill 归因以归一化 body hash 为对象身份，并让找不到上报对象的后处理 bad case 有明确的“最后”语义，而不是依赖运行时缓存路径或缺失锚点的出生点兜底。

## 范围

对象 revision、tag 解析为内容 hash、Session 关联、后处理触发点、缓存键、契约/UI 展示、parser 版本与重放、测试与迁移；实现前先完成设计文档评审。

## 验收

对象身份不再包含运行时 source path；选择 tag 能解析出与轨迹 definitionHash 相同的 body hash；找不到对象的后处理 case 使用显式的后处理触发点并按“对象之后”参与潜在匹配；旧 path+body revision 有明确兼容与重放边界；相关设计文档、Note 与测试计划一致。

## 非目标

不改变 knowledge 目标的 revision 语义；不引入私有仓库凭据；不重写归因引擎 rule-v1 的分类逻辑；不在设计文档评审前落地代码。
