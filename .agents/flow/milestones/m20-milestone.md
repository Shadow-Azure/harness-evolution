# M20 启动向导 Session 关联展示修复

[English](m20-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m20
title: M20 启动向导 Session 关联展示修复
status: planned
github:
  number: 28
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/28
```

## 目标

让「启动自进化」第 2 步「Session 关联」在 1440 宽视口下四列同屏：Session 单元格显示短标签、单行省略与完整标题悬停提示，保留 Session 短 ID；长 prompt 不再撑宽表格或把关联证据列推出弹窗。

## 范围

预览接口 `SessionPreviewItem` 的短标题字段、`LaunchWizard.vue` 的会话单元格与表格横向布局、共享契约生成、API 与组件测试、m10-05 浏览器 E2E、设计文档与 Agent Note。

## 验收

- 1440 宽视口、720 宽弹窗内 `Session`、`对象出现`、`对象触发点时间`、`该 Session 的 bad case 数` 四列同时可见，长标题不产生横向滚动。
- Session 单元格显示短标签并通过 `title` 提供完整标题；Session 短 ID 保留。
- 预览接口返回 `short`（来源 `session_families.short_title`）与完整 `title`。
- Session 关联、bad case 统计、分页与排序不变；组件测试与 E2E 覆盖长标题回归。
- PR 描述含修复前后的真实应用截图与 V2 原型同区域对照。

## 非目标

不改 `short_title` 生成算法、Session 关联算法或统计口径；不对齐条件条 chip、统计行项数或完整 UUID 展示；不把生产 Session 内容提交进仓库。
