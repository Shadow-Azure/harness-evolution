# 「Session 错误查看」页出现第三条页面滚动条，与 V2 原型和壳层滚动契约不一致

[English](bugfix-session-third-scrollbar.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-02
milestone: bugfix
depends:
  - m22-02
priority: P2
status: ready
scope:
  - apps/web/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 434
  url: https://github.com/Shadow-Azure/harness-evolution/issues/434
```

## 背景

2026-11-20，用户在生产「Session 错误查看」页（`/workspaces/{wid}/sessions/{sid}`，1500×837 CSS 视口）报告页面同时出现三条纵向滚动条：左栏 Session 列表一条、右栏内容一条、以及窗口最右侧多出来的一条。用户明确要求只保留左边和右边各一条，不要第三条。

用户截图（1500×837 @2x）：

![生产「Session 错误查看」页：三条纵向滚动条](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-problem.png)

右侧边缘放大后可以确认第三条是页面（窗口）滚动条，不是某个卡片自己的滚动条：

![右侧边缘放大：右栏滚动条与窗口滚动条并排](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-problem-right-edge.png)

现场可读出的事实：

- 截图里页面已经整体向下滚动：左栏「Session 浏览器」标题、搜索与筛选，以及右栏 Session 标题、统计与执行流顶边都不在画面里；左栏列表滚动条轨道在 y≈406 结束，说明整个会话浏览页（文档）滚动了约 400–500px，而不是左栏列表自己滚。
- 画面最右侧的窗口滚动条把右栏 `.overview` 的滚动条挤到左侧约 17px，两条灰色滚动条并排；按窗口滚动条 thumb 约占 353/837 估算，文档可滚动高度约为视口的 1.5–1.9 倍。
- 用户红框圈出的两栏下方空白带，是两栏内容结束之后仍继续存在的页面背景区域，来自同一次整页滚动。

这不是该页应有的滚动结构。[08 §5.5](../../../plans/fullstack-design/08-frontend-implementation.md) 规定会话浏览页根节点固定视口高度、文档本身不滚动，左栏 `.sidebar` 与右栏 `.overview` 各自是唯一的滚动容器——也就是恰好两条。V2 原型同页同视口也只有两条，见下文对照。

## 目标

- 生产「Session 错误查看」页在常见桌面视口（至少 1500×837、1440×900、1366×768）只出现左栏列表与右栏内容两条纵向滚动条，页面（文档）本身不滚动，也不再能滚到两栏下方的空白带。
- 把「文档不滚动 + 恰好两条滚动条」从隐含约定变成可回归的断言，壳层高度链再次失配时 e2e 能直接变红。
- 不改 API 契约、Session 数据与内容结构，不改 V2 原型。

## 设计依据

- [08 §5.5 壳层高度与右栏填充](../../../plans/fullstack-design/08-frontend-implementation.md)：`.session-browser` 固定为窗口高度，文档不滚动，左右栏各自内部滚动；右栏内容不足一屏时由最后一个问题列表填满。
- V2 原型 `plans/ui-prototype-v2/harness-evolution.html`（`?u=admin&page=session&ws=ws-harness`）：`.shell` 高度为 `calc(100vh / var(--ui-zoom) - 56px)`，body 顶部固定偏移 56px，`.session-list` 与 `.main` 各自内部滚动，页面本身不滚动。
- 现状实现：`apps/web/src/App.vue` 的 `main.workspace-main`；`apps/web/src/pages/sessions/Index.vue` 的 `.session-browser`；`apps/web/src/pages/sessions/components/SessionOverview.vue` 的 `.overview`。
- 前序工作：[#415](https://github.com/Shadow-Azure/harness-evolution/issues/415) 记录同一页底部的空白带与窗口级滚动；[#422](https://github.com/Shadow-Azure/harness-evolution/issues/422)（m22-02）修复低内容填充，并把「文档不滚动」写进 e2e。

## 对照与复现

同页、同 1500×837 视口、同为低内容 Session 的三方对照：

| 项目 | 生产截图（用户提供） | V2 原型 | 当前 main |
|---|---|---|---|
| `document.scrollingElement.scrollHeight` / `innerHeight` | 约 1.5–1.9 × | 837 / 837 | 837 / 837 |
| 纵向滚动容器 | 左列表 + 右栏 + 窗口 | `.session-list` + `.main` | `.session-list` + `.overview` |
| 页面整体可滚动 | 是（截图已下滚） | 否 | 否 |
| 两栏下方空白带 | 有（红框） | 无 | 无（右栏内容填满） |

- V2 原型同视口截图（只有左右两条，`document` 837 = 视口 837）：

![V2 原型同页同视口：只有两条滚动条](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-prototype.png)

- 当前 main 同视口截图（fixture Session，document 837 = 视口 837，只有左右两条）：

![当前 main 同页同视口：只有两条滚动条](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-current-main.png)

当前 main 的实测值（headless Chrome，1500×837，fixture Session）为：`document.scrollHeight = 837 = innerHeight`，满足条件的滚动容器只有 `.session-list`（scrollHeight 752 / clientHeight 607）与 `.overview`（835 / 781）两个；原型为 `.session-list`（2237 / 554）与 `.main`（824 / 756）两个。两者都没有窗口滚动条。

因此生产截图与当前 main 不一致：截图仍带着 #422 修复前的两栏下方空白带，而 #422 已在 2026-11-20 13:17 随 `1890e2d7` 部署。需要先在生产上排除构建版本因素（硬刷新后复验并记录构建 hash）；但无论截图来自旧构建还是某个未覆盖的状态，「第三条滚动条」都说明这条不变量目前只靠页面高度链的隐式配合，没有显式断言兜底。

## 实现内容

- 把 Session 页高度收敛到一个 owner：`main.workspace-main` 提供 `100dvh`（`100vh` 回退）高度与 `overflow: hidden`；`.session-browser` 改用 `height: 100%`，不再自己重复计算 `calc(100vh/dvh - var(--shell-header-height))`，保留 `min-height: 0`。≤860px 单列断点仍为 `height: auto; overflow: visible`（移动端允许文档滚动）。
- 在 `tests/e2e/m3-session-browser.test.mjs` 增加显式断言：
  - `document.scrollingElement.scrollHeight === innerHeight`；
  - `window.scrollTo(0, 500)` 后 `window.scrollY === 0`；
  - 遍历所有元素，`overflow-y` 为 `auto|scroll` 且 `scrollHeight > clientHeight + 1` 的顶层滚动容器恰好 2 个，并分别命中 `.session-list` 与 `.overview`；
  - 覆盖 1500×837、1440×900 与右栏滚到底（内容超长）三种状态。
- 更新 [08 §5.5](../../../plans/fullstack-design/08-frontend-implementation.md) 与同 PR 的 Agent Note，写明「恰好两条滚动条、文档不滚动」的契约与验证方式。
- 生产复验若仍复现，采集 `document.scrollingElement.scrollHeight`、`innerHeight`、全部滚动容器及其 rect、构建 hash，补进 issue 后再改布局。

## 实施步骤

1. 用生产构建（不是 dev server）在 1500×837 复验并记录构建 hash；若硬刷新后不再出现，保留第 3 步的回归断言与第 4 步的文档，不改布局。
2. 收敛高度来源：`main.workspace-main` 负责视口高度与裁剪，`.session-browser` 用 `height: 100%`。
3. 补 m3 e2e 的文档不滚动与滚动容器计数断言。
4. 更新 08 §5.5 与 Agent Note，写清「左右各一条、页面不滚」。
5. 跑门禁，取 1500×837 Before/After 截图（三条 → 两条），在生产硬刷新后复验。

## 依赖与交付边界

- 依赖：m22-02（Session 页填充与「文档不滚动」回归基线）。
- 不涉及 API、数据口径、Session 内容结构；不改 V2 原型；不把生产 Session 截图提交进仓库，证据只放 issue/Release 附件。
- 若生产复验确认截图来自旧构建，本 issue 仍交付第 1、3、4 项（复现记录、回归断言、契约文档），不为了「看起来改了」而重排布局。

## 独立验证

```sh
pnpm typecheck:web
pnpm lint:web
pnpm test:web
node --test tests/e2e/m3-session-browser.test.mjs
pnpm verify:flow
pnpm lint:docs
```

- e2e 在 1500×837 与 1440×900 下通过：文档高 = 视口高，`scrollY` 恒 0，顶层纵向滚动容器恰为 2。
- 生产硬刷新后同视口只看得到左栏与右栏两条滚动条；构建 hash 记录在 PR。

## 验收标准

- 生产「Session 错误查看」页在 1500×837、1440×900、1366×768 下仅左右两条纵向滚动条，页面不可滚动。
- 第三条不再出现；若再次出现，e2e 能变红。
- 低内容与超长内容两种状态都成立；移动端 ≤860px 单列仍可正常文档滚动。
- 原型对照图、当前 main 复现记录与生产构建 hash 留在 issue/PR。

## 门禁与 CI

- 命中 `pnpm test:e2e`（m3 Session 浏览器）、`pnpm typecheck:web`、`pnpm lint:web`、`pnpm verify:flow`、`pnpm lint:docs`。
- 新断言并入现有 e2e 用例，不新增独立慢测。

## 非目标

- 不重做 Session 页布局，不调整左右栏宽度或视觉样式。
- 不改 V2 原型与其它页面（运行详情页的滚动容器由 [#423](https://github.com/Shadow-Azure/harness-evolution/issues/423) 单独跟踪）。
- 不用 `body { overflow: hidden }` 之类的方式只把第三条隐藏掉而不修高度链。
- 不重开或改写 #415 已关闭的低内容空白带工作。
