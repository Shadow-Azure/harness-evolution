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

截图里页面已经整体下滚：左栏「Session 浏览器」标题、搜索与筛选，以及右栏 Session 标题、统计与执行流顶边都不在画面里；红框区域是两栏结束后的页面背景空白带。

## 生产复验与根因

2026-11-20 15:00 前后，用生产环境（http://8.149.232.63/，管理员账号）复验同一 Session `5f4a5c96-d4bf-4781-b5c5-291c6b5b21ea`：

- 生产部署的 `assets/index-CYlO1h4q.js` 与本地 `pnpm build` 的 main 构建哈希完全一致，排除旧构建/缓存因素。
- 1500×837、dpr 2 实测：`document.scrollingElement.scrollHeight = 1895`，`clientHeight = 837`（约 2.26 屏），窗口滚动条占宽 15px。
- `.shell` 高 837、`main.workspace-main`、`.session-browser`、`.sidebar`、`.overview` 都是 781 高、底边 837；满足 `overflow-y: auto` 且 `scrollHeight > clientHeight` 的只有 `.session-list`（1843 / 607）与 `.overview`（952 / 781）两个。
- 页面上没有任何可见元素越过 837，但把 `.session-list` 设 `display: none` 后 `document` 立刻回到 837；逐张隐藏 Session 卡，`document` 高度按一张卡的高度（约 179px）递减；最后一张卡的 `span.sr-only` 位于 y≈1830，`document` 高度 1895 正好由它决定。

根因在 `apps/web/src/pages/sessions/components/SessionCard.vue` 的无障碍状态文本：

- `.sr-only` 使用 `position: absolute`，而 `.session-card`、`.session-list` 都没有定位祖先，计算出的 `offsetParent` 是 `body`。
- 绝对定位盒子的包含块是初始包含块；`.session-list` 的 `overflow-y: auto` 不在它的包含块链上，因此**不会裁剪它**。它的静态位置（每张卡片标题行的高度）被直接计入根元素的 scrollable overflow。
- 生产列表有 10 条 Session，最后一张卡的 `.sr-only` 落在 y≈1830，把文档撑到 1895；可见布局仍然是 837，浏览器于是画出窗口滚动条，页面可以滚到两栏下方的空白带。用户截图里的第三条滚动条和空白带都来自这里。

为什么之前没有复现：#415/#422 与 m3 e2e 的合成数据只有 4 条 Session；4 张卡时最后一个 `.sr-only` 仍在 837 以内，`document` 保持 837。生产 10 条才越过视口，所以 #422 的低内容填充没有碰到这个溢出源，回归也一直是绿的。

修复已在生产页面上做过内存验证：给 `.session-card` 加 `position: relative` 后，`document.scrollHeight` 从 1895 立即变为 837，`scrollWidth = clientWidth = 1500`，可滚动容器只剩 `.session-list` 与 `.overview`，`window.scrollTo(0, 600)` 后 `scrollY` 保持 0。Before / After：

![生产复验：修复前 document 1895，窗口滚动条存在](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-prod-verify.png)

![生产复验：注入修复后 document 837，只剩左右两条滚动条](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-prod-fixed.png)

## 目标

- 生产「Session 错误查看」页在 1500×837、1440×900、1366×768 只出现左栏列表与右栏内容两条纵向滚动条，文档本身不滚动，不再能滚到两栏下方的空白带。
- 把「文档不滚动 + 恰好两条滚动条」变成覆盖 10 条以上 Session 的可回归断言，避免同类绝对定位元素在没有定位祖先时再次撑高文档。
- 审计同类 `.sr-only` 用法，避免在其它滚动容器里复现同一问题。
- 不改 API 契约、Session 数据与内容结构，不改 V2 原型。

## 设计依据

- [08 §5.5 壳层高度与右栏填充](../../../plans/fullstack-design/08-frontend-implementation.md)：`.session-browser` 固定为窗口高度，文档不滚动，左右栏各自内部滚动。
- V2 原型 `plans/ui-prototype-v2/harness-evolution.html`（`?u=admin&page=session&ws=ws-harness`）：`.shell` 高度为 `calc(100vh / var(--ui-zoom) - 56px)`，body 顶部固定偏移 56px，`.session-list` 与 `.main` 各自内部滚动，页面本身不滚动。
- 受影响的实现：`apps/web/src/pages/sessions/components/SessionCard.vue`（`.sr-only`）、`apps/web/src/pages/sessions/Index.vue`（`.session-browser`）、`apps/web/src/pages/sessions/components/SessionOverview.vue`（`.overview`）。
- 前序工作：[#415](https://github.com/Shadow-Azure/harness-evolution/issues/415) 记录同一页的空白带与窗口级滚动；[#422](https://github.com/Shadow-Azure/harness-evolution/issues/422)（m22-02）修复低内容填充并加了「文档不滚动」回归，但合成数据只有 4 条 Session，没有覆盖本溢出。

## 对照与复现

| 项目 | 生产（实测） | V2 原型 | 当前 main（4 条 fixture） |
|---|---|---|---|
| `document.scrollHeight` / `innerHeight` | 1895 / 837 | 837 / 837 | 837 / 837 |
| 纵向滚动容器 | 左列表 + 右栏 + 窗口 | `.session-list` + `.main` | `.session-list` + `.overview` |
| 页面整体可滚动 | 是 | 否 | 否 |
| 两栏下方空白带 | 有 | 无 | 无 |

- V2 原型同视口（只有左右两条，`document` 837 = 视口 837）：

![V2 原型同页同视口：只有两条滚动条](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-prototype.png)

- 当前 main 同视口、4 条 fixture Session（`document` 837 = 视口 837）：

![当前 main 同页同视口：4 条 Session 时只有两条滚动条](https://github.com/Shadow-Azure/harness-evolution/releases/download/session-triple-scrollbar-evidence-20261120/session-third-scrollbar-current-main.png)

## 实现内容

- `SessionCard.vue`：给 `.session-card` 加 `position: relative`，让卡片里的 `.sr-only` 以卡片为包含块，重新被 `.session-list` 的 `overflow-y: auto` 裁剪；不改可见布局与无障碍文案。
- 审计 `AttributionReport.vue`、`VersionLabel.vue` 等使用 `.sr-only` 的位置：若它们位于滚动容器内且同样没有定位祖先，按相同方式收口（给最近的卡片/行容器加 `position: relative`，或把 `.sr-only` 放进一个已定位的包裹节点）；在 08 §5.5 补一句「滚动容器内的 `.sr-only` 必须有定位祖先」。
- `tests/e2e/m3-session-browser.test.mjs`：在现有 4 条 Session 的 1500×837 场景克隆到 10 张卡片（测完移除，不改共享 fixture），断言：
  - `document.scrollingElement.scrollHeight === innerHeight`；
  - `window.scrollTo(0, 500)` 后 `window.scrollY === 0`；
  - 顶层 `overflow-y: auto|scroll` 且 `scrollHeight > clientHeight + 1` 的容器恰为 `.session-list` 与 `.overview` 两个；
  - 所有 `.session-card .sr-only` 的 `offsetParent` 不是 `body`（直接锁住本次根因）。
- 在 08 §5.5 与同 PR 的 Agent Note 记录「sr-only 必须落在滚动容器内的定位祖先上」的契约与验证方式。
- 生产修复后硬刷新复验，附 Before / After 截图与构建 hash。

## 实施步骤

1. 给 `.session-card` 增加 `position: relative`，先在生产页面上按上述注入方式复验 `document` 回到 837。
2. 审计其它 `.sr-only` 用法，按同一规则收口。
3. 在 m3 e2e 克隆到 10 张卡片（测完移除）：先在未修复代码上确认变红，再修复转绿。
4. 更新 08 §5.5 与 Agent Note。
5. 跑门禁、取 Before / After 截图，生产硬刷新复验。

## 依赖与交付边界

- 依赖：m22-02（Session 页填充与「文档不滚动」回归基线）。
- 不涉及 API、数据口径、Session 内容结构；不改 V2 原型；不把生产 Session 截图提交进仓库，证据只放 issue/Release 附件。
- 修复需要重新部署并在生产硬刷新后验收；`position: relative` 不改变可见布局。

## 独立验证

```sh
pnpm typecheck:web
pnpm lint:web
pnpm test:web
node --test tests/e2e/m3-session-browser.test.mjs
pnpm verify:flow
pnpm lint:docs
```

- e2e 在 10 条 Session、1500×837 与 1440×900 下通过：文档高 = 视口高，`scrollY` 恒 0，顶层纵向滚动容器恰为 2，`.sr-only` 的 `offsetParent` 不是 `body`。
- 生产硬刷新后同视口只有左栏与右栏两条滚动条，`document.scrollingElement.scrollHeight` 等于 `innerHeight`。

## 验收标准

- 生产「Session 错误查看」页在 1500×837、1440×900、1366×768 下仅左右两条纵向滚动条，页面不可滚动。
- 第三条不再出现；未修复代码上新增的 10 条 Session 回归会变红。
- 低内容与超长内容、10 条 Session 三种状态都成立；移动端 ≤860px 单列仍可正常文档滚动。
- 同类 `.sr-only` 位置已审计并记录结论。

## 门禁与 CI

- 命中 `pnpm test:e2e`（m3 Session 浏览器）、`pnpm typecheck:web`、`pnpm lint:web`、`pnpm verify:flow`、`pnpm lint:docs`。
- 新断言并入现有 e2e 用例，不新增独立慢测。

## 非目标

- 不重做 Session 页布局，不调整左右栏宽度或视觉样式。
- 不用 `body { overflow: hidden }` 之类的方式只把第三条隐藏掉而不修根因。
- 不改 V2 原型与其它页面（运行详情页的滚动容器由 [#423](https://github.com/Shadow-Azure/harness-evolution/issues/423) 单独跟踪）。
- 不重开或改写 #415 已关闭的低内容空白带工作。
