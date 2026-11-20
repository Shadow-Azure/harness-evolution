# M23 运行列表与原型对齐

[English](m23-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m23
title: M23 运行列表与原型对齐
status: active
github:
  number: 32
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/32
```

## 目标

把「自进化 → 历史记录」运行卡片的运行配置信息补齐到 V2 原型与设计文档 05 §3.5 的口径：对象版本与时间窗之后显示工作空间、潜在策略、缓存三枚标签；卡片不再显示创建人前缀，创建人只保留在 DTO；历史卡的结构与六项统计不回归。

## 范围

`apps/api/app/service/evolution/runs.py` 及其测试、`packages/contracts` 生成物、`apps/web/src/pages/evolution/**`、`tests/e2e/**`、`plans/ui-prototype-v2/harness-evolution.html`、`plans/fullstack-design/05-api-design.md` 与 `08-frontend-implementation.md`、`scripts/doc-budgets.manifest.json`，以及对应的流程文件与 Agent Note。后续运行列表与 V2 原型的同源展示偏差沿用本 milestone。

## 验收

历史卡片依次显示对象版本、时间窗、工作空间、默认 / 自定义潜在策略、复用 / 不复用缓存，顺序与 V2 原型一致；契约含 `policy.preset` 与 `cacheEnabled` 且由后端投影，旧 run 无策略时按默认策略展示；卡片右上只显示时间，创建人保留在 DTO 而不在列表渲染；completed 运行仍有 best / 初始 / Δ / 接纳行，failed 运行不伪造终评数据；契约、类型、单测、API 测试与聚焦 E2E 通过；Before / After 截图同视口且附在 PR。

## 非目标

不改运行详情页、启动向导、对象配置与归因步骤内容；不改数据库 schema、归因 / 聚类 / 评测算法、SSE、七步 key 与分页；不重做列表页布局或页面宽度；不把生产 Session 内容或截图提交到仓库。
