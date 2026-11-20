# 运行详情页缺少滚动容器导致内容被裁切，页边距也偏离 V2 原型

[English](bugfix-run-detail-scroll-gutter.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-01
milestone: bugfix
depends:
  - m21-01
priority: P2
status: done
scope:
  - apps/web/**
  - tests/e2e/**
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr: []
github:
  number: 423
  url: https://github.com/Shadow-Azure/harness-evolution/issues/423
```

## 背景

### 问题场景

生产「自进化 → 运行详情」在常见笔记本视口下整页被裁切：页面停在「第 5 步 · 聚类与严重度」的簇列表中间，下方内容不可见；浏览器不出现纵向滚动条，鼠标滚轮、PageDown、End 与 `window.scrollTo` 均无效，只能缩小浏览器 zoom 才能看到更多内容。截图对应的运行停在 clone 失败阶段、当前查看第 5 步；相同布局在 1366×768、1440×900、1500×837 都能复现，1920×1080 因内容高度刚好不超过首屏而不触发纵向裁切，但左右仍然通栏。

复现路径：`/workspaces/<wid>/evolution` → 历史记录中任一条运行 → 运行详情；把浏览器视口设为 1500×837（与截图 3000×1674 @2x 等效）。

### 现场测量

以生产 1500×837 CSS 视口为例（同一运行、同一第 5 步，用 Playwright 读取计算样式）：

| 视口 | `main` 可视高 | `.run-detail-page` 内容高 | 溢出 | 滚轮后 `scrollY` | 文档 `scrollHeight` |
|---|---:|---:|---:|---:|---:|
| 1366×768 | 712 | 1006 | 294 | 0 | 768 |
| 1440×900 | 844 | 1006 | 162 | 0 | 900 |
| 1500×837 | 781 | 1006 | 225 | 0 | 837 |
| 1920×1080 | 1024 | 1006 | 0 | 0 | 1080 |

- `document.scrollingElement.scrollHeight === clientHeight`，页面本身没有可滚动高度；`main.workspace-main` 的 `scrollHeight` 是 1006、`clientHeight` 是 781，但 `overflow-y: hidden`；页面内也没有任何 `overflow-y: auto|scroll` 的滚动容器。所以这里不是“滚动条被隐藏”，而是整页确实没有滚动行为。
- 滚轮、PageDown、End、`window.scrollTo(0, 1000)` 四种方式执行后 `window.scrollY` 与所有元素的 `scrollTop` 都保持 0。
- 页面内容高 1006 只覆盖当前运行已渲染的一个簇和展开的来源 bad case 表；簇更多或展开更多行时内容更高，裁切会继续放大。

### V2 原型对照

在本地以同一 1500×837 视口打开 `plans/ui-prototype-v2/harness-evolution.html` 的运行详情（`#/run/EV-20261109-01`，同样停在第 5 步）：

- 原型由文档滚动：`document.scrollingElement.scrollHeight = 1474`，`clientHeight = 837`；滚轮一次后 `scrollY = 637`，可以一直滚到页面底部。
- 原型内容容器 `.evo-app .wrap` 为 `width: min(100%, calc(1720px / var(--ui-zoom, 1)))`、`margin: 0 auto`、`padding: 20px 24px 64px`；1500×837 下详情内容左边界 25px、宽 1450px；1440×900 下左边界 24px、宽 1392px；1920×1080 下容器 1720px 居中、左边界 130px、宽 1660px。
- 生产运行详情没有这层页容器：`.run-detail-page` 直接挂在 `main.workspace-main` 下，1500 视口下左边界 0、宽 1500px，1920 视口下宽 1920px，卡片左右贴边；同一视口下左右留白生产为 0，原型为 24–25px（1500）、130px（1920），这是截图里“没有 V2 原型舒服”的直接原因。
- 生产内部也不一致：同一应用的「自进化」列表、对象配置、空间管理使用 `.evolution-page-frame`（`width: min(1080px, 100%)` + 24px 内边距，1500 视口下左边界 210px、宽 1080px）；只有运行详情既没有 1080 框架，也没有原型的 1720 页宽，成为全宽孤例。

### 根因

1. `apps/web/src/App.vue` 的 `main.workspace-main` 把工作空间页固定为 `height: calc(100vh - var(--shell-header-height))` 且 `overflow: hidden`，文档本身不滚动；滚动责任被下放给每个页面。
2. `apps/web/src/pages/overview/Index.vue` 的 `.overview-page` 与 `apps/web/src/pages/workspaces/Admin.vue` 的 `.admin-page` 都按这个约定提供了 `height: 100%; overflow-y: auto` 的页级滚动容器；`apps/web/src/pages/evolution/RunDetail.vue` 的 `.run-detail-page` 只有 `display: grid; gap: 14px`，没有高度与滚动声明。内容超过 `main` 的可视高度后，超出部分直接被 `main` 裁掉，页面内又没有第二层滚动容器，于是既没有滚动条也无法滚动。
3. `.run-detail-page` 没有像列表/配置/管理页那样套 `.evolution-page-frame`，直接继承 `main.workspace-main` 的 100% 宽度与 0 内边距，因此运行详情是全宽通栏。m21-01 的运行详情重排改变了卡片层级与内容高度，但保留了没有滚动容器、没有页宽容器的根节点；当前运行在 1500×837 下内容高 1006px，超过 `main` 的 781px。

### 影响

- 运行详情的第 5 步簇列表、第 6/7 步内容和日志页签在笔记本视口下无法完整查看，用户只能改浏览器 zoom 或换更大的显示器。
- 页面左右贴边与同应用其他页面、V2 原型都不一致，视觉密度偏高；视口越宽，与原型 1720 页宽的差异越大。
- 这是前端布局回归，不涉及数据或执行结果；刷新、换浏览器、放大缩小之外的交互都无法绕过。

## 目标

- 运行详情在 1366×768、1440×900、1500×837 等常见视口下可以正常纵向滚动，滚轮、PageDown、End 都能到达页面底部，不再被 `main` 裁切。
- 运行详情补齐页级内容容器：默认按 V2 原型 `.wrap` 的 `min(100%, 1720px)` + 24px 左右内边距居中，恢复与原型一致的左右留白；滚动条落在窗口右缘，而不是嵌在卡片内部。
- 不改变运行详情的信息层级、字段集、页签、步骤内容与数据口径；不改变 Session 浏览器、总览、空间管理等其他页面的滚动行为。
- 用组件测试或 E2E 固化“可滚动 + 页边距”两个回归点，避免下一次重排再次把内容推过折叠线而无滚动容器。

## 设计依据

- [08 §10.1 运行详情结构 / §10.2 交互](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L740-L800)：运行详情是单列卡片流，包含页头、页签、目标与输入、流程进度、当前步骤产出；步骤内容可以很长，页面必须可滚动到最后一个簇。
- [V2 原型运行详情](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L5423-L5446)：`evRenderDetail()` 把详情放进 `.wrap`；[`.evo-app .wrap`](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L606) 定义 `width: min(100%, 1720px)`、`margin: 0 auto`、`padding: 20px 24px 64px`，页面由文档滚动。
- [V2 前端原型设计 §2.1](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/design-v2.md)：详情沿用 V1 的 panel/stepper/cluster 组件，不引入第二套布局语言。
- [现有页级滚动实现](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/web/src/pages/overview/Index.vue#L607-L615)：`.overview-page` 用 `height: 100%; overflow-y: auto` + 对称内边距把滚动条留在窗口右缘，是本 issue 要复用的应用内模式。

## 实现内容

- `apps/web/src/pages/evolution/RunDetail.vue`：把 `.run-detail-page` 变成页级滚动容器——`height: 100%`、`overflow-y: auto`、底部 64px 内边距；左右内边距按 V2 原型取 `max(24px, calc((100% - 1720px) / 2 + 24px))`，使内容在 1720px 处封顶并居中，滚动条仍落在 `main` 的窗口右缘。
- 同步调整 `RunDetail` 的窄屏断点：≤640px 时左右内边距回落到 12–16px，避免小屏出现双重留白；`height: 100%` 在 `main.workspace-main` 的移动端 `height: auto` 分支下改为 `height: auto` 或保持文档滚动（与 overview 的移动端处理一致）。
- 不改组件的 DOM 层级与数据逻辑；优先只动根节点样式。如果评审要求显式内容容器，可把现有卡片包进一个 `.run-detail-inner`，但需要在 PR 说明中选择一种并保持单一实现。
- 回归测试：在 `apps/web/src/pages/evolution/RunDetail.test.ts` 或新增 E2E 中覆盖页级滚动容器的存在与内容可达性；E2E 在 1440×900 / 1500×837 下断言 `.run-detail-page` 的 `scrollHeight > clientHeight`、滚轮或 End 后 `scrollTop > 0` 且到达底部，并断言左右内边距/内容宽度符合 1720 页宽规则。
- 若实现选择沿用现有 `.evolution-page-frame` 的 1080 页宽而不是原型的 1720，必须在 PR 中说明理由，并同步更新本 issue 的验收口径；默认推荐按原型 1720 对齐。

## 实施步骤

1. 在 `RunDetail.vue` 根节点补页级滚动与页宽内边距，确认 `main.workspace-main` 的 `overflow: hidden` 不再裁切内容；必要时在模板外层加一个内容容器。
2. 处理 ≤640px 断点，确认移动端不会出现 `height: 100%` 与文档滚动叠加的双滚动条。
3. 补组件/E2E 断言：滚动容器存在、内容可达底部、1500/1920 视口下左右留白符合预期。
4. 在本地起生产同构页面，用 1366×768、1440×900、1500×837、1920×1080 四个视口做 Before/After 截图与滚动验证；Before 明确标注当前基线版本。
5. 运行聚焦单测、类型检查、lint、E2E 与流程门禁；PR 描述附 Before/After 对比与测量数据。

## 依赖与交付边界

- 依赖：m21-01（运行详情已按 V2 原型重排；本 issue 只修布局滚动与页边距，不回退其字段与层级）。
- 交付边界：只改 `apps/web` 的运行详情样式与对应测试；不改 API、契约、归因/聚类/评测算法、SSE、七步 key、步骤内容组件。
- 不把生产运行 ID、Session 内容或生产截图提交到仓库；Before/After 截图只放 PR 描述或本地证据，不进入 fixtures。
- 列表/配置/空间管理页仍使用 1080 页宽，本 issue 不顺手改它们；如果产品确认要统一到原型 1720，另开 issue 或在本 issue 的 PR 中单独说明范围。

## 独立验证

```sh
pnpm --filter @harness/web exec vitest run src/pages/evolution/RunDetail.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "m10-06"
pnpm verify:flow
```

- 在 1500×837 视口打开生产同构的运行详情：`.run-detail-page` 的 `scrollHeight` 大于 `clientHeight`；滚轮一次后 `scrollTop > 0`；按 End 后 `scrollTop + clientHeight` 与 `scrollHeight` 差值 ≤2px。
- 在 1500×837 与 1920×1080 视口测量根节点左右内边距：1500 下为 24px，1920 下为 124–130px；内容宽度不超过 1720px。
- 1366×768、1440×900 下同样可滚到底；Session 浏览器与总览页不出现双滚动条，滚动行为不变。
- 单测、类型检查、lint、聚焦 E2E 与 `pnpm verify:flow` 全绿。

## 验收标准

- 1366×768、1440×900、1500×837 视口下，运行详情可用滚轮、PageDown、End 从页头滚到最后一个簇和底部内边距；`main` 不再裁切内容，页面内不存在“内容高于可视区但无滚动容器”的状态。
- 1500×837 下运行详情内容左右各留 24px；1920×1080 下内容区在 1720px 处封顶并居中；与 V2 原型同视口对照，左右留白差异 ≤6px。
- 运行详情的页头、页签、目标与输入、流程进度、步骤产出、日志页签的顺序和字段不变；m21-01 的验收项不回退。
- 既有页面（Session 浏览器、总览、空间管理、自进化列表/配置）滚动行为与页宽不变。
- 修复 PR 附同场景、同视口、同主题的 Before/After 截图，Before 标注基线提交；不提交生产截图到仓库。
- 最终验收由提出人确认：在提出人确认整条流程暂时没有发现问题之前，本 issue 不关闭；修复 PR 只交付可复核的实现与证据。

## 门禁与 CI

- 单测与覆盖率：`pnpm test:web`（至少覆盖 `RunDetail.test.ts`）。
- 类型与 lint：`pnpm typecheck:web`、`pnpm lint:web`。
- E2E：`pnpm test:e2e -- "m10-06"`，必要时新增本 issue 的滚动回归用例。
- 流程：`pnpm verify:flow`；PR 标题与提交带 `(#<本 issue 编号>)`。
- 文档：若改动设计文档或原型，补跑 `pnpm lint:docs`；默认不改原型与设计文档。
- CI 全绿后交付人工检视；本 PR 由人合并。

## 非目标

- 不改运行详情的 DOM 信息层级、字段集、页签默认值、步骤 key、分页与执行日志数据源。
- 不改 API、`packages/contracts`、归因/聚类/评测算法、SSE 与任务调度。
- 不重做 V2 原型、不调整设计 token、不统一改列表/配置/空间管理页的 1080 页宽。
- 不通过隐藏滚动条、`overflow: clip` 或压缩内容高度来“修复”裁切。
- 不把生产运行 ID、Session 内容、截图或凭据写入仓库。
