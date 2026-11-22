# 自进化列表页缺少页级滚动容器，运行卡超过首屏即被裁切

[English](bugfix-evolution-list-scroll.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-15
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - apps/web/**
  - tests/e2e/**
  - tests/support/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-22-evolution-list-page-scroll.md
github:
  number: 496
  url: https://github.com/Shadow-Azure/harness-evolution/issues/496
```

## 背景

2026-11-22 生产「自进化」列表页（`/workspaces/<wid>/evolution`）在 1408×788 CSS 视口下无法向下滚动。现场有 3 张执行中与 5 张历史运行卡，列表内容高 1348px，而工作区壳层 `main.workspace-main` 的可视内容区只有 732px；`main` 以固定高度和 `overflow: hidden` 裁掉超出部分，列表根节点 `.run-list-page` 只有 `display: grid; gap: 14px`，没有 `height` 或 `overflow-y`，文档本身也不滚动。滚轮、PageDown、End 与 `window.scrollTo` 都无法移动页面，浏览器右侧没有滚动条；用户只能改 zoom 或换显示器。

同壳层的总览页 `.overview-page`、空间管理页 `.admin-page` 与运行详情 `.run-detail-page` 都按既定契约提供 `height: 100%; overflow-y: auto` 的页级滚动；只有自进化列表（及同样使用 `.evolution-page-frame` 的对象配置页）没有补齐。V2 原型由文档滚动，列表再长也能撑高文档。完整的现场测量、截图与根因分析见 GitHub #496。

## 目标

- 自进化列表页在 1366×768、1408×788、1440×900、1500×837、1920×1080 下都能纵向滚动，滚轮、PageDown、End 与拖动滚动条都能到达最后一张历史卡。
- 滚动条落在窗口右缘；内容列继续保持 1080px 框架（1032px 内容 + 左右 24px 内边距），不产生横向位移或第二层滚动条。
- 只改列表页的滚动归属，不改运行卡的数据、顺序、分组、字段、按钮和启动向导，也不改其它页面的滚动实现。
- 增加真实浏览器回归，覆盖“3 张执行中 + 5 张历史且视口受限”时的可滚动性与内容列位置。

## 设计依据

- [08 §8 自进化列表页](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L610-L633)：列表由页头、两组 RunGroup 与 N 张 RunCard 组成，设计未限制卡片数量。
- [08 §5 Session 浏览器页](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L482-L488)：工作区壳层的文档不滚动，页面内容区各自承担滚动。
- [08 §10 运行详情页](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L761-L765)：页面根节点以 `height` + `overflow-y: auto` 承担页级滚动，是本 issue 复用的模式。
- [V2 原型列表渲染](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L5233-L5250)：卡片直接渲染进内容容器，内容高度自然撑开文档。
- [#362 总览滚动条落点](https://github.com/Shadow-Azure/harness-evolution/issues/362) 与 [#423 运行详情页级滚动](https://github.com/Shadow-Azure/harness-evolution/issues/423)：同应用已确认“页级滚动 + 滚动条在窗口右缘”的方向。

## 实现内容

- 在 `apps/web/src/styles/main.css` 的 `.workspace-main .evolution-page-frame` 规则之后新增 `.workspace-main .run-list-page`：`height: 100%`、`width: 100%`、`overflow-y: auto`，左右内边距取 `max(24px, calc((100% - 1080px) / 2 + 24px))`，上下内边距沿用 20px / 64px。全宽节点让滚动条画在窗口右缘，对称内边距保持 1080px 框架与 1032px 内容列。
- 新增 ≤640px 覆盖：`height: auto`、`overflow-y: visible`、`padding: 8px 24px 0`，跟随 `main.workspace-main` 的移动端文档滚动分支，避免内外双层滚动条。
- 扩展 `tests/e2e/m5-run-list.test.mjs`：在 1408×788、1366×768、1920×1080 下断言列表是唯一滚动容器、文档不滚动、滚动条右缘等于窗口、内容列左边界与宽度符合 1080px 框架，并用真实滚轮、PageDown、End 到达最后一张卡；在 390×844 下断言文档滚动且列表根节点不出现第二层滚动条。
- 更新 `plans/fullstack-design/08-frontend-implementation.md` §8 的滚动归属说明，并新增 Agent Note 记录页级滚动与 1080px 框架的取舍。

## 实施步骤

1. 在 `apps/web/src/styles/main.css` 增加列表页页级滚动规则与 ≤640px 覆盖。
2. 扩展 `tests/e2e/m5-run-list.test.mjs` 的滚动与内容列回归。
3. 更新 08 §8，并新增 Agent Note 三件套后运行 `pnpm record:i18n`。
4. 运行聚焦 E2E、`pnpm test:web`、`pnpm typecheck:web`、`pnpm lint:web`、`pnpm verify:web-style`、`pnpm verify:docs` 与 `pnpm verify:flow`。
5. 在 1408×788 下采集同场景、同主题的 Before/After 截图与测量值，PR 标题带 `(#496)`。

## 依赖与交付边界

- 依赖：无外部资源、无 API / 契约 / 数据库 / 鉴权变更。
- 交付边界：`apps/web/**`、`tests/e2e/**`、`tests/support/**`、`plans/**`、`.agents/**`。
- 进化对象配置页仍使用 `.evolution-page-frame` 且没有页级滚动容器；本 issue 只作用于 `.run-list-page`，不顺手改对象配置页，统一两者需另开 issue。
- 不把生产 URL、账号、密码、运行数据或截图写入仓库；Before/After 证据只放 PR 描述或发布资产。

## 独立验证

```sh
pnpm test:e2e -- "m5-run-list"
pnpm test:web
pnpm typecheck:web
pnpm lint:web
pnpm verify:web-style
pnpm verify:docs
pnpm verify:flow
```

- 在 1408×788 下 `.run-list-page` 的 `scrollHeight` 大于 `clientHeight`，三次滚轮后 `scrollTop > 0`，End 后 `scrollTop + clientHeight` 与 `scrollHeight` 差值 ≤2px；`document.scrollingElement.scrollHeight === clientHeight`。
- 滚动容器的右缘与 `window.innerWidth` 相差 ≤2px；1408 下左内边距约 188px、内容列约 1017–1032px，1920 下左内边距约 444px、内容列仍约 1017–1032px。
- 1366×768 与 1920×1080 下同样可滚到底；390×844 下 `document` 可滚动、列表根节点 `scrollHeight === clientHeight`。
- 上述命令全部通过；`verify:web-style` 无新增颜色 token。

## 验收标准

- 1408×788 下滚轮、PageDown、End、拖动滚动条都能到达最后一张历史卡，右侧滚动条位于窗口右缘。
- 首屏顶部布局不变：内容列左边界、宽度、卡片间距与页头位置不产生横向位移。
- 1366×768、1440×900、1500×837、1920×1080 下均能到达列表底部；640px 以下不出现内外双层滚动条。
- 新增的真实浏览器回归在修复前失败、修复后通过；不修改运行数据、接口返回、卡片顺序或启动向导行为。
- PR 描述包含 1408×788 的 Before/After 截图与关键测量值，并链接本 issue；Agent Note 与文档门禁通过。

## 门禁与 CI

- E2E：`pnpm test:e2e -- "m5-run-list"`，并纳入 CI 的 `pnpm test:e2e`。
- 单测与覆盖率：`pnpm test:web`（覆盖率 ≥80%）。
- 类型与 lint：`pnpm typecheck:web`、`pnpm lint:web`、`pnpm verify:web-style`。
- 文档与流程：`pnpm verify:docs`、`pnpm verify:flow`；PR 标题与提交带 `(#496)`。
- 合并前需要 1 名 reviewer 检视；CI 全绿后交付人工检视，本 PR 由人合并。

## 非目标

- 不重做列表的信息架构、卡片样式、分组口径、筛选、分页或无限滚动。
- 不改运行详情、仅聚类、对象配置、总览或空间管理页的滚动实现。
- 不改 `main.workspace-main` 的固定壳层、顶栏高度或全局 `overflow`。
- 不把页宽从 1080px 改为 1720px；页宽与滚动是两个独立问题。
- 不隐藏滚动条、不压缩卡片内容、不要求用户改 zoom 或换显示器。
- 不修改生产数据、接口、契约、鉴权或部署配置。
