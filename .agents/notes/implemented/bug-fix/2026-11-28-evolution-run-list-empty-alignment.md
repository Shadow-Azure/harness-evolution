# Agent Note: 自进化列表空状态按内容高度排列

Status: implemented

[English](2026-11-28-evolution-run-list-empty-alignment.en.md) | 中文

## Problem

当前空间没有自进化运行时，`/workspaces/<wid>/evolution` 的页头说明与「正在执行（0）」之间、分组标题与空卡之间出现大面积纵向留白，两个空卡也明显高于单行提示所需高度（[GitHub #669](https://github.com/Shadow-Azure/harness-evolution/issues/669)）。

列表根节点 `.run-list-page` 用 `display: grid` 布局，`main.css` 又给它 `height: 100%` 与 `overflow-y: auto`，让它在固定高度、隐藏溢出的 `.workspace-main` 内承担页级滚动（#496）。网格容器未设置 `align-content`，默认值 `normal` 在内容高度之外还有剩余空间时按 `stretch` 处理：页头、两个分组三行自动轨道平分剩余高度，行内元素随之拉伸。空卡 `.waiting` 是分组的网格项，`align-items: stretch` 让它填满被拉高的行。

浏览器实测（1366 宽，`main` 高 712/1024，均为 `height: 100%` 的列表容器）：空列表时页头从 179.8px 长到 283.8px，空卡从 111.5px 长到 163.5px，页头到首个分组标题的间距从 145.9px 长到 249.9px。3/5 记录的内容超过视口，没有剩余空间，所以同一份代码在长列表下正常——这解释了为什么只有空/少量记录时出现留白。

## Decision

`.workspace-main .run-list-page` 保留 `height: 100%` 与 `overflow-y: auto`，增加 `align-content: start`：三行自动轨道按内容高度从内容盒顶部排列，剩余高度留在滚动容器底部，不再分配给轨道。分组与卡片仍按原有 `gap` 和内容高度布局；空卡继续使用自身 `15px 16px` 内边距，不写死高度。

≤640px 时壳层已把高度交还文档、列表 `height: auto`，此行不改变移动端滚动归属；长列表本来就没有剩余空间，行为不变。

## Alternatives considered

- **移除 `height: 100%` 或改为 `min-height`**：会让列表重新参与文档滚动，破坏 #496 已确定的页级滚动与窄屏滚动契约；拒绝。
- **只加 `align-items: start`**：能阻止单项在行内拉伸，但自动轨道仍会平分剩余高度，行与行之间依旧出现空带；拒绝。
- **给空卡写死 `height` 或 `max-height`**：能压矮这一种状态，但提示换行、字体缩放或未来文案变化时会截断；拒绝，尺寸继续由内容决定。
- **把页面网格改成 flex 或给每行 `min-content`**：改动面更大，且与现有 `gap`、页头结构无收益；拒绝。

## Consequences

- 空列表和少量记录时页头、分组标题、空卡从顶部连续排列；1366×768 与 1366×1080 下空卡高度、相邻间距不再随视口变化。
- 空卡保持约 51px 的内容高度，不再出现百像素级空带；两个分组的标题、零计数、提示与启动入口不变。
- 长列表仍由列表根节点滚动到最后一项；移动端仍由文档滚动，不产生嵌套滚动。
- 只改列表容器的纵向对齐，不涉及运行数据、API、契约、卡片字段或全局壳层。
