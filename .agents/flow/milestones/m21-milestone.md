# M21 运行详情与原型对齐

[English](m21-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m21
title: M21 运行详情与原型对齐
status: done
github:
  number: 29
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/29
```

## 目标

把「自进化 → 运行详情」页面的层级、字段集与统计口径收敛回 V2 原型和设计文档 08 §10：页头只保留标题、状态与空间 badge；工作区、推送与评测信息并入「目标与输入」折叠区；「流程进度」紧跟「目标与输入」，其后是当前步骤产出；执行日志页签与准备中态在生产与原型中都可见。

## 范围

`apps/web/src/pages/evolution/RunDetail.vue` 及其组件测试、`tests/e2e/m10-06-run-detail-v2.test.mjs`、`plans/ui-prototype-v2/harness-evolution.html`、`plans/fullstack-design/08-frontend-implementation.md`，以及对应的流程文件与 Agent Note。后续运行详情与 V2 原型的同源展示偏差沿用本 milestone。

## 验收

页头为标题 + 状态 + 空间 badge；目标与输入含工作空间、关联 Session、时间段内 bad case、潜在 bad case、可归因 / 非该对象与策略 / 缓存徽标；工作区信息在工作区折叠区内且分支名可复制；流程进度位于目标与输入之后；分布标题与图例按潜在 bad case 口径；七步详情 / 执行日志页签与准备中态在生产与原型都可见；不改 API 契约与执行算法；聚焦门禁与 Before / After 截图齐备。

## 非目标

不改归因、聚类、评测算法、API 契约、SSE、七步 key 与分页；不改步骤内容组件、自进化列表、启动向导与对象配置；不把生产 Session 内容或截图提交到仓库。
