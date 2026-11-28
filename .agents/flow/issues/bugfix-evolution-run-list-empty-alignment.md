# 自进化列表空状态按内容高度顶部排列，消除视口拉伸留白

[English](bugfix-evolution-run-list-empty-alignment.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-75
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - apps/web/src/pages/evolution/**
  - apps/web/src/styles/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-28-evolution-run-list-empty-alignment.md
github:
  number: 669
  url: https://github.com/Shadow-Azure/harness-evolution/issues/669
```

## 背景

用户截图显示，当前空间没有自进化运行时，`/workspaces/<wid>/evolution` 的页头说明与「正在执行（0）」之间、分组标题与空卡之间存在大面积纵向留白，两个空卡也显著高于单行提示所需高度。截图未现场测量 CSS 像素，复现时以浏览器计算样式和元素边界为准。

当前 `.run-list-page` 使用 `display: grid`，`apps/web/src/styles/main.css` 又为其设置 `height: 100%` 承担工作区壳层内的页级滚动；网格容器没有显式设置内容纵向对齐，默认的 `align-content: normal` 会在行高之外分配剩余空间，空列表和少量记录时把页头、分组与提示卡拉成视口高度。`#496` 解决多卡片滚动、`#415/#422` 解决 Session 页低内容空白，均未覆盖本问题。

## 目标

- 空列表及少量记录时，页头、分组标题和提示卡按内容高度从顶部连续排列，间距不随视口高度膨胀。
- 保留两个分组的标题、零计数、空提示与启动入口。
- 固定宽度增加视口高度时，相邻区块间距及空卡高度变化不超过 2 CSS px。
- 长列表滚动、窄屏文档滚动与无横向溢出均不回归。

## 设计依据

- [08 §8 自进化列表页](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L612)：页头、RunGroup 与 RunCard 的结构，以及列表根节点承担页级滚动的契约。
- [V2 原型自进化列表](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html)：分组标题、空提示与卡片按普通文档流从上到下排列，不填充剩余视口。
- [#496](https://github.com/Shadow-Azure/harness-evolution/issues/496)：保持页级滚动与窄屏滚动契约。

## 实现内容

检查页面与分组的 grid 轨道、`align-content`、`min-height` 和空卡样式后，针对确认的拉伸来源收紧纵向布局：列表根节点在保留 `height: 100%` 页级滚动的同时，让网格内容从顶部按轨道内容高度排列；空卡保持自身内边距，不再随容器高度拉伸。复用既有间距 token，不隐藏分组、不取消滚动。

补充浏览器回归：使用 0/0、0/1、1/0、1/1、3/5 的合成运行数据，在 1366×768、1920×1080、390×844 视口验证内容顶部排列、空卡高度与相邻间距不随视口高度变化，并保留长列表滚动覆盖。

## 实施步骤

1. 用合成空间复现并采集元素边界及计算样式，确认拉伸来源。
2. 添加能捕获纵向拉伸的浏览器回归，再局部修正样式。
3. 同视口对比截图，回归长列表滚动，补齐设计说明与 Agent Note。

## 依赖与交付边界

- 依赖：无阻塞依赖；关联 #496。
- 范围为自进化列表布局、对应浏览器回归与设计说明，不涉及 API、契约或运行数据。

## 独立验证

```sh
pnpm test:e2e -- m5-run-list
pnpm typecheck:web
pnpm lint:web
pnpm verify:web-style
pnpm verify:flow
```

- 新回归在修复前失败、修复后通过；空卡高度与相邻间距在 1366×768 与 1366×1080 之间的差异不超过 2 CSS px。
- 3/5 数据下长列表仍滚动到最后一项，390×844 由文档滚动且无横向溢出。
- 类型、lint、样式与流程门禁通过；PR 提供修复前后同视口截图和几何测量。

## 验收标准

- 空列表的页头、两组标题和空提示从顶部自然排列，没有被剩余高度拉开的空带。
- 固定宽度将高度从 768 调到 1080 时，相邻区块间距及空卡高度变化不超过 2 CSS px（相同缩放、字体与文案）。
- 空卡保留合理内边距；启动入口、零计数和提示可见，单组为空与少量记录同样紧凑。
- #496 的长列表及移动端滚动不回归；PR 提供修复前后同视口截图和几何测量。

## 门禁与 CI

- 聚焦 E2E 纳入现有 CI；运行前端单测、类型、lint、样式、文档与流程门禁，覆盖率不低于 80%。

## 非目标

- 不修改运行逻辑、权限、API、卡片字段、全局壳层或其他页面。
- 不通过隐藏空分组或取消滚动来掩盖问题。
