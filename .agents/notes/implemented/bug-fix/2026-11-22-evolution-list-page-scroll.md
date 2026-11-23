# Agent Note: 自进化列表页级滚动与 1080px 框架

Status: implemented

[English](2026-11-22-evolution-list-page-scroll.en.md) | 中文

## Problem

工作区壳层 `main.workspace-main` 固定 `height: calc(100vh - var(--shell-header-height))` 且 `overflow: hidden`，滚动责任下放给各页面。总览页 `.overview-page`、空间管理页 `.admin-page` 与运行详情 `.run-detail-page` 都提供了 `height: 100%; overflow-y: auto` 的页级滚动容器；自进化列表的根节点 `.run-list-page` 只复用了 `.evolution-page-frame` 的页宽与内边距，仍只有 `display: grid; gap: 14px`。当列表累计到 3 张执行中 + 5 张历史、内容高 1348px 时，超出 `main` 732px 可视高度的 616px 被直接裁掉，滚轮、PageDown、End 与 `window.scrollTo` 都无效，文档的 `scrollHeight` 等于 `clientHeight`。现场测量见 GitHub #496。

V2 原型由文档滚动，内容多高页面就多高；生产把文档滚动换成固定壳层后，列表页没有完成同一契约的迁移，于是成为唯一没有页级滚动入口的列表页。页宽 1080px 与滚动是两个独立问题，本决策只补滚动归属。

## Decision

- 列表页根节点承担页级滚动：在 `apps/web/src/styles/main.css` 为 `.workspace-main .run-list-page` 声明 `left: 0`、`width: 100%`、`height: 100%`、`margin: 0`、`overflow-y: auto`，左右内边距取 `max(24px, calc((100% - 1080px) / 2 + 24px))`，上 20px、下 64px。
- 节点保持全宽，常显纵向滚动条画在 `main` 的窗口右缘；对称内边距让 1080px 框架继续居中，内容列在 1408 视口下保持约 1032px（overlay 滚动条）或 1017px（经典 15px 滚动条），首屏顶部不产生横向位移。
- ≤640px 跟随 `main.workspace-main` 的 `height: auto; overflow: visible` 分支：根节点改为 `height: auto; overflow-y: visible`、内边距 `8px 24px 0`，由文档滚动，避免内外双层滚动条。
- 只改样式与真实浏览器回归，不改模板结构、卡片组件、数据流或启动向导；`m5-run-list` 在 1408×788、1366×768、1920×1080 下断言唯一滚动容器、文档不滚动、滚动条右缘、内容列几何与真实滚轮 / PageDown / End 可达性，并在 390×844 下断言文档滚动。
- 对象配置页（`pages/evolution/targets/Index.vue`）同样缺页级滚动，但本决策只覆盖 `.run-list-page`；统一两者需独立 issue 与验收。

## Alternatives considered

- **保留 1080px 框架宽度并只加 `height: 100%; overflow-y: auto`**：改动更小，滚动条会落在 1080px 内容列的右缘；1408 视口下距窗口右缘约 164px，与 #362/#423 已确认的窗口右缘落点不一致。拒绝。
- **把 `main.workspace-main` 的 `overflow: hidden` 改成 `overflow-y: auto`**：一行即可让所有无自带滚动的页面获得滚动，但同时改变总览、Session、错误详情与空间管理的滚动归属，需要重新验证双层滚动条，超出本 issue 的局部修复边界。拒绝。
- **在列表模板里增加内层滚动容器或内容容器**：需要多一层 DOM 与间距重算，收益只是把滚动与页宽分离；根节点样式已经能同时满足两个目标，改动面更小。拒绝。
- **隐藏滚动条、压缩卡片高度或要求用户改 zoom**：只让裁切不可见，没有恢复内容可达性，违反 issue 的验收标准。拒绝。

## Consequences

- 自进化列表在 1366×768 到 1920×1080 的桌面视口下都能滚到最后一张历史卡，滚动条位于窗口右缘，内容列位置与修复前一致。
- 总览、空间管理、运行详情、Session 浏览器与对象配置页的滚动实现不变；对象配置页仍可能在内容超过首屏时被裁切，需另开 issue 处理。
- ≤640px 由文档滚动；若将来修改 `main.workspace-main` 的移动端高度 / 溢出分支，列表页断点样式必须同步。
- 真实浏览器套件 `m5-run-list` 新增滚动与内容列回归，继续使用合成 fixture，不读取生产运行或用户截图。
