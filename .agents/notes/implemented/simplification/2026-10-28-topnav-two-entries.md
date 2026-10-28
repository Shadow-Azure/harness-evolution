# Agent Note: 顶栏信息架构回归原型两入口

Status: implemented

[English](2026-10-28-topnav-two-entries.en.md) | 中文

## Problem

m1-09 脚手架为占位引入 Sessions/Errors/Evolution 三入口与顶层 `/errors` 路由（单测当时即声明 "top-level errors entry arrives later"），m2-09 对齐原型时只对齐了视觉系统，把"Sessions/Errors/Evolution 下划线式导航"写进验收固化至今。而原型的信息架构是两入口：错误详情是 Session 视图内部的子页。后果是顶层 Errors 成了死胡同——`/errors` 只渲染"请选择会话"空态，背后没有跨会话错误列表 API，页面上也没有任何动作可走；同时 `/sessions/:sid` 与 `/sessions/:sid/errors` 上三个导航项全部不高亮（vue-router 的 `router-link-active` 只认 matched 路由记录，平铺兄弟路由不做前缀匹配），偏离原型"Session 页签在子页保持激活"。

## Decision

- 顶栏只保留两入口：Session 错误查看（副标题"会话轨迹与归因"）与自进化（副标题"报告驱动的迭代优化"），右侧恢复 ID 串联说明；<1100px 隐藏副标题与说明（原型同规则）。
- 激活态改为 TopNav 内按路径前缀计算（`/sessions*` → 蓝、`/evolution*` → 紫），不再依赖 `router-link-active`；路由结构保持平铺不动。
- 顶层 `/errors` 退役为 `redirect: "/sessions"`；ErrorsPage 的无参空态分支及其样式删除，错误工作区成为页面唯一形态。错误详情的唯一入口是 Session 卡片/概览与自进化深链 `/sessions/:sid/errors?case=&tab=`。

## Alternatives considered

- 保留三入口，把 Errors 做成真页：需要新增跨会话 bad-case 列表 API 与契约变更，而设计文档（F1"两大视图切换"、路由表只登记 `/sessions/:sid/errors`）从不支持顶层 `/errors`；为一个导航占位开后端能力不值。否——先退役入口，未来需要时另立 issue。
- 路由改嵌套（`/sessions` 为父、`:sid` 与 `:sid/errors` 为 children）让 `router-link-active` 天然生效：需要引入只做 `<RouterView/>` 透传的父组件，并同步 workspace meta 与恢复路径，改动面远大于收益。否——TopNav 内按前缀计算即可。
- 让 `/errors` 直接渲染错误工作区并自动选中首项：仍是无会话上下文的死页，且与"错误详情属于 Session 视图"的原型结构相悖。否。

## Consequences

- 旧书签与外链访问 `/errors` 落到 `/sessions`，不再出现占位页；`reports/2026-10-26/m4-04-error-detail/collect-smoke.mjs` 里访问 `/errors` 的取证步骤会落在 Sessions（历史取证脚本，不随本变更修改）。
- `ui-prototype.test` 锁定的导航契约从三入口改为两入口；后续若新增顶层视图（如时间线独立成页），需同时改该契约与本 Note。
- 跨会话错误总览仍是产品空白：未来若需要，走新 issue（API + 契约 + 页面一起做），不复用 `/errors` 路径。
