# M14 问题卡展示与原型对齐

[English](m14-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m14
title: M14 问题卡展示与原型对齐
status: active
github:
  number: 22
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/22
```

## 目标

把 V2 原型验收暴露的展示偏差收敛回原型：Session 页问题列表卡以问题描述为主体，补齐类型/对象徽章、完整 case ID、关联行与定位入口，归因状态只保留轻量标识。

## 范围

Session 页问题列表卡的非 compact 模板与样式、其单测与 E2E、V2 原型同源渲染、设计文档与证据截图；后续同源展示偏差沿用本 milestone。已知待收敛项：类型徽章的配色与填充沿用错误详情页，与原型样式表相反。

## 验收

未分析与已分析 case 的列表卡都显示问题描述；卡片含 BC 编号、类型/对象徽章、完整 case ID、关联行与「定位 ↗」；错误详情页、接口、数据模型与归因逻辑不变；聚焦门禁与 Before/After 截图齐备。

## 非目标

不重做问题列表的信息架构，不改归因状态机、API、数据模型与错误详情页，也不把生产 Session 内容写入仓库。
