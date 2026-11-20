# Agent Note: Session 卡片 sr-only 逃出滚动裁剪

Status: implemented

[English](2026-11-20-session-card-sr-only-containment.en.md) | 中文

## Problem

生产「Session 错误查看」页出现第三条窗口滚动条（[GitHub #434](https://github.com/Shadow-Azure/harness-evolution/issues/434)）。1500×837 下 `document.scrollingElement.scrollHeight = 1895`、`clientHeight = 837`；页面所有可见容器的底边都在 837，隐藏 `.session-list` 后文档立刻回到 837。

根因是 `SessionCard.vue` 的状态文本 `<span class="sr-only">` 使用 `position: absolute`，而 `.session-card` 与 `.session-list` 都没有定位祖先，元素的 `offsetParent` 因此是 `body`。绝对定位盒子的包含块变成初始包含块，`.session-list` 的 `overflow-y: auto` 不在它的包含块链上，裁剪对它不生效；它按卡片标题行的静态位置计入根元素的 scrollable overflow。生产 10 条 Session 时最后一张卡的 `.sr-only` 落在 y≈1830，把文档撑到 1895，浏览器于是画出窗口滚动条，页面可以滚到两栏下方的空白带。

当时的回归没有覆盖：m3 e2e 与合成 fixture 只有 4 条 Session，最后一张卡的 `.sr-only` 仍在 837 以内，`document` 保持 837，所以 #422 的「文档不滚动」断言一直是绿的。

## Decision

给 `.session-card` 加 `position: relative`，让 `.sr-only` 以卡片为包含块，重新被 `.session-list` 的 `overflow-y: auto` 裁剪；卡片可见布局与无障碍文案不变。按同一规则审计其它页面的 `.sr-only`：`AttributionReport.vue` 的 `.attribution` 与 `VersionLabel.vue` 的 `.version-label` 同样补 `position: relative`。

m3 e2e 在同一 1500×837 场景下补两类断言：`.session-card .sr-only` 的 `offsetParent` 不能是 `body`；把列表克隆到 10 张卡片后，`document.scrollingElement.scrollHeight` 必须等于 `innerHeight`。克隆只用于制造 10 张卡片的布局，测完移除，不改共享 fixture。

`plans/fullstack-design/08-frontend-implementation.md` §5.5 记录规则：滚动容器内的绝对定位辅助文本（`.sr-only`）必须以该容器内的元素为包含块。

## Alternatives considered

- **给 `body` 或 `html` 加 `overflow: hidden`**：能隐藏第三条滚动条，但会连带影响总览、自进化等需要文档滚动的页面，也没有修根因；拒绝。
- **把 `.sr-only` 改成 `position: static`**：能避免逃逸，但会在 flex 行里占一个 1px 的布局位置、可能改变对齐，而且三个组件的 `.sr-only` 各自内联；拒绝，保留标准视觉隐藏写法，补定位祖先。
- **把 fixture 扩到 10 条 Session**：共享 fixture 的条数被多个用例断言，改动面与副作用都超出这个布局缺陷；布局回归与数据来源无关，测试内克隆真实卡片即可复现 10 条布局；拒绝。
- **只加文档高度断言**：4 条 Session 时文档本来是 837，测不出；必须用 `offsetParent` 直接锁住根因；拒绝。

## Consequences

- 生产页文档回到 837，只剩左栏与右栏两条滚动条；卡片与右栏的可见布局不变。
- 在未修复代码上，新断言会红：4 个 `.sr-only` 的 `offsetParent` 是 `body`，10 张卡片布局下文档高约 1895；修复后为 0 与 837。
- 新增约定：滚动容器内新增 `.sr-only` 时必须确认它落在容器内的定位祖先上，否则它的静态位置会把文档撑高。
- `.sr-only` 仍可能被其它没有定位祖先的容器复用；后续新增位置按上述规则检查，未做全局 lint。
