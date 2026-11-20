# Session 页低内容时填满视口

[English](m22-session-browser-low-content-fill.en.md) | 中文

```yaml flow
kind: issue
id: m22-02
milestone: m22
depends:
  - m3-01
priority: P2
status: in-progress
scope:
  - apps/web/src/pages/sessions/**
  - tests/e2e/**
  - plans/**
  - .agents/**
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/implemented/bug-fix/2026-11-20-session-browser-viewport-fill.md
github:
  number: 422
  url: https://github.com/Shadow-Azure/harness-evolution/issues/422
```

## 背景

2026-11-20 的生产「Session 错误查看」页在一个只有 1 个用户轮次、1 条消息、0 次工具调用、0 个子 Agent、1 条 bad case 的 Session 上出现右侧内容提前结束、下方留出大块页面背景空白的问题；同视口的 V2 原型没有这条空白带。完整对照与截图见 [GitHub #415](https://github.com/Shadow-Azure/harness-evolution/issues/415)。

当前 main 的 Session 页壳层已经固定为 `100vh - 顶栏`，文档不滚动，问题卡列表也在右栏内部滚动，用同规模合成 Session 无法复现生产截图里的整页滚动与 300–550px 空白带。可在当前 main 复现的剩余缺口有两个：右栏 `.overview` 撑满，但内容少于一屏时内容仍从顶部自然结束，空白留在右栏背景；执行流是异步分片，分片未到时组件不渲染任何内容，右栏先塌成只有标题的高度，问题列表上方没有占位。前一个缺口在更高视口、执行流失败或缺失时出现，后一个缺口在每次首屏都会短暂出现。

## 目标

- Session 页根节点拥有视口高度：`100dvh`（`100vh` 回退）减去顶栏，文档本身不滚动，左栏与右栏各自内部滚动。
- 右栏在内容不足一屏时由最后一个问题列表填满剩余高度；内容超过一屏时列表保持自然高度，由右栏滚动，不拉伸问题卡正文。
- 执行流的接口加载、接口失败、无数据以及异步分片加载 / 失败五种状态都保留与原型同量级的全高占位，右栏不因执行流未就绪而提前结束。
- 1500×837 与 1500×1100 两个视口都有回归断言；移动端 ≤860px 的单列自然高度不回归。
- 不改 API 契约、Session 数据与问题卡内容结构。

## 设计依据

- [08 §5.5 壳层高度与右栏填充](../../../plans/fullstack-design/08-frontend-implementation.md)：`.session-browser` 的视口高度、滚动归属、右侧填充与执行流占位。
- [08 §5.1–5.2 组件树与交互](../../../plans/fullstack-design/08-frontend-implementation.md)：左栏、右栏、执行流与问题列表的职责。
- V2 原型 `plans/ui-prototype-v2/harness-evolution.html`：`.shell` 固定视口高度，`.sidebar` 与 `.main` 撑满，`.rf-canvas` 使用 `clamp(420px, calc(100vh - 280px), 720px)`，`.finding-list` 底部内边距 24px。
- [GitHub #415](https://github.com/Shadow-Azure/harness-evolution/issues/415)：生产截图与差异对比。

## 实现内容

- `apps/web/src/pages/sessions/Index.vue`：`.session-browser` 增加 `100dvh` 高度（保留 `100vh` 回退）与 `min-height: 0`；右栏兜底错误态补 `min-height: 0`。
- `apps/web/src/pages/sessions/components/SessionOverview.vue`：`.overview` 改纵向 flex 且 `min-height: 0`；`.overview-content` 占满可用高度；最后一个 `.problem-list` 用 `flex: 1 0 auto` 在内容不足一屏时填满剩余高度；整体骨架 / 错误态与空态也参与填充。
- 同一组件：AgentFlow 的异步分片增加 loading / error 组件；执行流接口加载、失败与无数据分支统一使用桌面 720px、窄屏 420px 的 `.tree-loading` 占位，异步分片失败时显示失败提示而不是空白。
- `tests/e2e/m3-session-browser.test.mjs`：把低内容布局断言并入现有 Session 浏览器用例，断言 1500×837 文档不滚动、两栏底边贴视口、滚到底后最后内容距视口底 ≤24px；切到 1500×1100 后问题列表填满剩余高度且同样 ≤24px。
- `plans/fullstack-design/08-frontend-implementation.md`、V2 原型与 Agent Note 同步壳层与填充口径。

## 实施步骤

1. 固定 Session 页壳层高度并保持左右栏内部滚动，文档不滚动。
2. 把右栏改为可填充的纵向 flex 容器，最后一个问题列表在低内容时占满剩余高度。
3. 为执行流的异步分片、接口加载、接口失败与无数据状态补齐全高占位。
4. 在 `tests/e2e/m3-session-browser.test.mjs` 增加 1500×837 与 1500×1100 的低内容回归。
5. 更新设计文档、V2 原型口径与 Agent Note，生成 Before / After 与原型对照证据。

## 依赖与交付边界

- 依赖：m3-01（Session 浏览器骨架）。
- 不改 Session 列表 / 概览 API、数据口径、问题卡内容结构与归因链路。
- 生产截图里的整页滚动无法在当前 main 复现，本次修复可复现的右栏塌陷与低内容填空；生产构建哈希与部署版本确认不在本 issue 的代码交付内。
- 不把生产 Session 内容或截图提交进仓库。

## 独立验证

```sh
pnpm typecheck:web
pnpm lint:web
pnpm test:web
node --test tests/e2e/m3-session-browser.test.mjs
pnpm verify:flow
pnpm lint:docs
```

- `typecheck:web`、`lint:web`、`test:web` 通过。
- 低内容 E2E 在 1500×837 下 `document.scrollingElement.scrollHeight === innerHeight`，`.session-browser`、`.sidebar`、`.overview` 底边等于 `innerHeight`，右栏滚到底后问题列表底边距视口底 0–24px；1500×1100 下问题列表直接贴住视口底 0–24px。
- E2E 用例在修复前于 1500×1100 断言失败（实测间距 108.5px），修复后通过（实测 18px 左右）。

## 验收标准

- 1500×837、1 轮 / 1 消息 / 0 工具 / 0 子 Agent / 1 case：页面没有窗口级滚动条；左栏 Session 面板与右栏内容区都撑满视口；右栏滚到底后最后内容距视口底 ≤24px，没有 300–550px 空白带。
- 1500×1100 同规模 Session：问题列表占满剩余高度，最后内容距视口底 ≤24px。
- 执行流异步分片未到、接口加载、接口失败与无数据时，右栏都保留全高占位，不塌陷为只有标题的面板。
- 多 Agent Session、问题列表滚动、执行流切换与 390×844 单列布局无回归。
- PR 描述含生产 Before 截图、修复后 After 截图与 V2 原型同区域对照。

## 门禁与 CI

- `pnpm typecheck:web`、`pnpm lint:web`、`pnpm test:web`。
- `node --test tests/e2e/m3-session-browser.test.mjs` 与 CI 全量 E2E。
- `pnpm verify:flow`、`pnpm lint:docs`、`pnpm verify:web-style`。
- 提交与 PR 标题挂本 issue 的 `(#N)`；PR 关联 M23 milestone。

## 非目标

- 不改 Session 列表 / 概览的查询参数、统计口径与问题卡正文。
- 不为填满而拉伸问题卡或重排卡片内容。
- 不全局禁用 `body` 滚动，不影响总览、自进化等需要文档滚动的页面。
- 不把生产 Session 内容或截图提交到仓库。
