# Agent Note: 运行详情页级滚动与 V2 页宽

Status: implemented

[English](2026-11-20-run-detail-page-scroll.en.md) | 中文

## Problem

工作区壳层 `main.workspace-main` 固定 `height: calc(100vh - var(--shell-header-height))` 且 `overflow: hidden`，滚动责任下放给各页面。总览页的 `.overview-page` 与空间管理页的 `.admin-page` 都提供了 `height: 100%; overflow-y: auto` 的页级滚动容器，运行详情的 `.run-detail-page` 却只有 `display: grid; gap: 14px`。在 1366×768、1440×900、1500×837 下运行详情内容约 1018px，超过 `main` 的 712–844px 可视高度后被直接裁掉，滚轮、PageDown、End 与 `window.scrollTo` 都无法移动，浏览器也不出现纵向滚动条。

运行详情还直接继承 `main` 的 100% 宽度与零内边距，卡片左右贴边；同应用的列表/配置/管理页使用 1080px 的 `.evolution-page-frame`，V2 原型使用 1720px 的 `.evo-app .wrap`，运行详情成为两种页宽口径之外的孤例。问题与现场测量见 GitHub #423。

## Decision

- 运行详情根节点 `.run-detail-page` 自己承担页级滚动：`height: 100%`、`overflow-y: auto`，左右内边距取 `max(24px, calc((100% - 1720px) / 2 + 24px))`、上 20px、下 64px。它保持全宽，所以常显纵向滚动条画在 `main` 的窗口右缘；内容在 1720px 处封顶并居中，与 V2 原型 `.evo-app .wrap` 的 `width: min(100%, 1720px)`、`padding: 20px 24px 64px` 同视口对照。
- ≤640px 断点跟随 `main.workspace-main` 的 `height: auto; overflow: visible` 分支：根节点改为 `height: auto; overflow-y: visible`、内边距 `14px 12px 48px`，由文档滚动，避免内外两层滚动条。
- 只改根节点样式，不增加内容容器、不改 DOM 层级、字段集、页签与步骤组件；运行详情根节点的样式注释记录滚动归属与 1720px 页宽约定。
- E2E 在 1366×768、1440×900、1500×837、1920×1080 下断言滚动容器右缘等于窗口、左右留白为 24/124px、内容列 ≤1720px、`scrollHeight > clientHeight`，并用真实滚轮、PageDown 与 End 验证可到达底部；640px 下断言文档滚动且根节点不出现第二层滚动条。

## Alternatives considered

- **沿用 `.evolution-page-frame` 的 1080px 页宽**：与同应用列表/配置/管理页一致，但运行详情是七步卡片流，步骤内包含宽表格、簇卡与 diff，1080px 会明显压缩阅读宽度；issue 的设计依据明确以 V2 原型 1720px 为准，且在 1500 视口下 1720 页宽仍保留 24px 留白。拒绝。
- **把 `main.workspace-main` 改为文档滚动（去掉固定高度与 `overflow: hidden`）**：这会把滚动归属同时改到总览、空间管理与 Session 等所有工作区页面，超出本 issue 的交付边界。运行详情沿用总览已验证的“全宽内滚动容器”模式。拒绝。
- **隐藏滚动条、改用 `overflow: clip` 或压缩内容高度**：只是让裁切不可见，没有恢复内容可达性，issue 也明确禁止。拒绝。
- **新增 `.run-detail-inner` 内容容器承载页宽与内边距**：需要多一层模板并重算所有直接子节点的间距，收益仅是把滚动与内边距分离；根节点样式已经足够，改动面最小。拒绝。

## Consequences

- 运行详情在笔记本视口下可以滚到最后一个簇、第 6/7 步与日志页签；滚动条位于窗口右缘，左右留白与 V2 原型同视口相差不超过 6px。
- 总览、Session 浏览器、空间管理与自进化列表/配置的滚动行为与页宽不变；列表、配置、管理页仍是 1080px，统一到 1720px 需要独立 issue 与产品确认。
- 1920×1080 下内容加上下内边距约 1102px，超过 `main` 的 1024px，因此该视口也会出现纵向滚动；这是页容器补齐后的预期效果，不是回归。
- ≤640px 由文档滚动；若将来修改 `main.workspace-main` 的移动端高度/溢出分支，本页断点样式必须同步。
- 真实浏览器套件在 `m10-06` 新增一条滚动与页边距回归用例，继续使用合成 fixture，不读取生产运行或 Session 内容。
