# 总览页滚动条落在内容列内缘，距窗口右缘约 160px

[English](m12-16-overview-scroll-ownership.en.md) | 中文

```yaml flow
kind: issue
id: m12-16
milestone: m12
depends:
  - m12-08
  - m12-09
  - m12-10
priority: P1
status: in-progress
scope:
  - apps/web/src/pages/overview/Index.vue
  - tests/e2e/m8-04-overview.test.mjs
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
adr: []
github:
  number: 362
  url: https://github.com/Shadow-Azure/harness-evolution/issues/362
```

## 背景

2026-11-18 在生产总览页上，1500×837 CSS 视口、2× DPR、经典常显滚动条下，页面纵向滚动条没有贴在浏览器窗口右缘，而是落在 1180px 内容列的右缘，右侧留下约 160 CSS px 的空白带；用户报障并框出该位置。

在相同视口渲染 `plans/ui-prototype-v2/harness-evolution.html` 对照：原型由文档整体滚动，`documentElement.scrollHeight` 为 1391、`clientHeight` 为 837，内容列 `.v2-page .wrap` 宽 `min(100%, 1720px)` 并贴满可用宽度，滚动条位于窗口右缘 `x=1485–1500`。当前实现把工作区主体固定为 `height: calc(100vh - 56px)` 且 `overflow: hidden`（`apps/web/src/App.vue` 116–121 行），由总览页内部的 `.overview-page` 承担滚动；该容器 `width: min(1180px, 100%)`、`margin: 0 auto`、`overflow-y: auto`（`apps/web/src/pages/overview/Index.vue` 597–603 行），因此滚动条画在内容列右缘 `x=1326–1338`，距窗口右缘 160px；滚动条起点也从窗口顶部下移到 56px 顶栏以下。

该差异只在常显滚动条的平台上稳定可见。macOS 覆盖式滚动条空闲时会隐藏，所以此前的生产/原型证据截图没有暴露它；在 Windows 或“始终显示滚动条”的浏览器里，内缩的滚动条会持续可见。

## 目标

- 总览页的纵向滚动条回到浏览器窗口右缘，与 V2 原型的滚动归属一致。
- 保持 1180px 内容列居中、卡片宽度与现有信息架构不变。
- 滚动条出现时不在内容列右侧留下可交互的空白带，也不引入横向滚动或双滚动条。
- 1024px 单列断点与 640px 移动端行为不回归。

## 证据截图

**同视口滚动条位置对比（1500×837 CSS，2× DPR）**

[![总览页滚动条位置：V2 原型与当前实现对比](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-16-scrollbar-evidence/scrollbar-corner-compare.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-16-scrollbar-evidence/scrollbar-corner-compare.png)

**整页对比（上：V2 原型；下：当前实现）**

[![总览页整页对比](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-16-scrollbar-evidence/scrollbar-full-compare.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-16-scrollbar-evidence/scrollbar-full-compare.png)

原始截图：[V2 原型](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-16-scrollbar-evidence/proto-overview-1500x837.png) · [当前实现](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-16-scrollbar-evidence/app-overview-1500x837.png)。两张原始截图都在 1500×837 CSS、2× DPR、`--disable-features=OverlayScrollbar` 下截取；当前实现来自本地运行的当前前端（Vite dev server）与种子数据，布局与生产一致。

## 设计依据

- [08 §6 工作空间总览页（`pages/overview/Index.vue`，V2）](../../../plans/fullstack-design/08-frontend-implementation.md#6-工作空间总览页pagesoverviewindexvuev2)：总览页的结构、交互与三态。
- [V2 设计 §5 工作空间总览](../../../plans/ui-prototype-v2/design-v2.md#5-工作空间总览)：原型对指标、筛选、双视角和下钻的约定。
- [V2 原型总览](../../../plans/ui-prototype-v2/harness-evolution.html)：`.v2-page .wrap { width: min(100%, 1720px); margin: 0 auto }`，由文档整体滚动。
- [App.vue 工作区壳层](../../../apps/web/src/App.vue)：`main.workspace-main` 固定高度并隐藏溢出，是内滚动容器的来源。

## 实现内容

- 把纵向滚动职责从 `.overview-page` 移到全宽的工作区主体（或等价地把滚动交还文档），让滚动条绘制在窗口右缘；`.overview-page` 只保留 1180px 居中内容列与内边距。
- 保持固定顶栏与 `height: calc(100vh - 56px)` 的可用高度；滚动区域不得延伸到顶栏之上，不得出现双滚动条或横向滚动。
- 同步 `App.vue` 的 `main.workspace-main` 高度/溢出与总览页的滚动容器，避免滚动条被 `overflow: hidden` 裁掉。
- 在 E2E 中新增 1500×837 视口断言：总览滚动容器的右缘等于 `window.innerWidth`（±1px），页面仍可纵向滚动到列表底部，且 1024px/640px 断点无回归。
- 不修改数据、接口、URL 状态与筛选逻辑；若壳层改动不可避免影响其它工作区页面，在同一 PR 补回归证据。

## 实施步骤

1. 在 1500×837 下复现并记录 `.overview-page`、滚动容器与窗口右缘的几何差值。
2. 调整工作区壳层与总览页的滚动所有权，保留 1180px 内容列与现有卡片宽度。
3. 在 `tests/e2e/m8-04-overview.test.mjs` 中断言滚动条右缘贴窗口，并验证列表可滚动、无横向滚动。
4. 用常显滚动条浏览器重拍 V2 原型与实现的同视口对比图，作为 PR 的 Before/After 证据。
5. 运行聚焦 E2E、类型检查与 lint，按 `docs/review.md` 走 PR 检视。

## 依赖与交付边界

- 总览页主体由 m8-04 交付，页头、筛选与列表由 m12-08、m12-09、m12-10 交付；本问题不依赖新的 API、数据字段或权限。
- 交付边界：只改总览页的滚动归属与对应测试/证据；不改 1180px 内容列宽、卡片结构、数据与接口。
- 若共享壳层改动不可避免影响 Session 错误查看或自进化页的内滚动，必须在同一 PR 说明并补对应回归证据，不能静默扩大为全站布局重构。

## 独立验证

```sh
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- --pattern m8-04-overview
```

- 预期：类型检查与 lint 通过；E2E 在 1500×837 视口下断言总览滚动容器右缘等于视口右缘，列表可滚动，1024/640 断点不回归。
- 人工验证：常显滚动条浏览器中重拍原型与实现同视口截图，两者滚动条均贴窗口右缘。

## 验收标准

- 在 1500×837、常显滚动条下，总览页纵向滚动条贴窗口右缘，右侧无约 160px 空白带。
- 滚动条起点与原型一致（顶栏以下至窗口底部），滚动过程中不出现双滚动条或横向滚动。
- 内容列仍为 1180px 居中，卡片、筛选、列表的宽度与交互不变。
- 1024px 单列断点与 640px 移动端布局不回归。
- PR 内含刷新后的 Before/After 同视口对比截图。

## 门禁与 CI

- `pnpm test:e2e -- --pattern m8-04-overview`
- `pnpm typecheck:web`、`pnpm lint:web`
- PR 标题与提交信息含 `(#N)`，检视按 `docs/review.md`。

## 非目标

- 不重做总览视觉，不调整 1180px 内容列宽或卡片密度。
- 不改滚动条样式（原生/覆盖、宽度、颜色）。
- 不改 Session 错误查看、自进化、空间管理等其它页面的滚动布局；共享壳层的连带改动必须在本 issue 的验证范围内说明。
- 不处理数据量、接口或权限差异。
