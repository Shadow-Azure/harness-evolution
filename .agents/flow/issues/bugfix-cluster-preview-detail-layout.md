# 仅聚类页纵向拉伸与状态信息重复，统一详情页布局

[English](bugfix-cluster-preview-detail-layout.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-76
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
  - ../../notes/implemented/bug-fix/2026-11-28-cluster-preview-detail-layout.md
github:
  number: 674
  url: https://github.com/Shadow-Azure/harness-evolution/issues/674
```

## 背景

用户截图显示「自进化 → 仅聚类」准备中页面的返回入口、标题、模式说明和准备提示被大幅纵向拉开，页面在内容很少时仍占满视口，橙色模式说明与准备提示重复描述同一段流程。`ClusterPreview.vue` 根节点与运行详情一样使用 `display: grid` + `height: 100%` 承担页级滚动，但没有设置 `align-content`；网格默认会在自动行之间分配剩余高度，短内容时轨道被拉高，块间距随视口高度膨胀。`RunDetail.vue` 的低内容状态使用同一组布局声明，也需要确认不受同一机制影响。

状态区域还有语义重复：顶部 `status-banner` 已经用「准备中」徽标和进度文案描述流程，下方 `preparing` 卡再用标题和一段几乎相同的文案重复一次；模式说明使用大号橙色警告卡，对正常可选模式来说视觉权重过高。长对象名在标题旁的单行 chip 中也没有换行或截断约定，窄屏可能横向溢出。

## 目标

- 仅聚类页的返回入口、标题、模式说明、状态区和结果卡按内容高度从顶部自然排列，剩余空白留在内容下方；保留页级滚动与多簇可滚至末尾。
- 固定宽度、字体和缩放下，视口高度从 768 增至 1080，短状态卡高度与相邻区块间距变化不超过 2 CSS px。
- 准备流程只保留一个主体状态区；正常模式说明收为紧凑信息条，不再使用大面积橙色警告卡。
- 状态文案复用 `run.progress` 的真实字段与既有 token，不伪造进度；保留暂停、继续、重试与启动自进化条件，禁用原因可理解。
- 长对象名支持换行并在悬停时给出完整值，窄屏与长名称无横向溢出。
- 运行详情在低内容状态下同样从顶部排列，不因共享布局声明回归。

## 设计依据

- [08 §11 仅聚类页](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#11-仅聚类页pagesevolutionclusterpreviewvue)：banner 文案、输入概况、聚类列表和页级滚动契约；仅聚类不执行 patch/评测。
- [08 §10 运行详情页](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#10-运行详情页pagesevolutionrundetailvue)：详情页的页头、状态徽标、信息卡与流程进度密度，是本 issue 对齐的现有实现。
- [V2 原型](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html)：页头、panel、cluster 卡按普通文档流从上到下排列，不填充剩余视口；仅聚类页复用运行详情第 5 步的 cluster 组件。
- [#669](https://github.com/Shadow-Azure/harness-evolution/issues/669)：自进化列表已用 `align-content: start` 解决同一类网格拉伸，本 issue 沿用该结论而不再重复探索布局方案。

## 实现内容

- `apps/web/src/pages/evolution/ClusterPreview.vue`：根节点保留 `height: 100%`、`overflow-y: auto` 与 1720px 内容列，增加 `align-content: start`，让自动行按内容高度从顶部排列；≤640px 断点继续交还文档滚动。
- 状态语义：页头徽标与单一状态区承担状态表达；准备中不再额外渲染重复的 `preparing` 卡，状态副文案取 `run.progress.stageLabel`（准备态回退到真实的五步流程描述）；失败/阻塞/中断在状态区内展示原因，不再另起标题重复。
- 模式说明改为紧凑信息条：保留「仅聚类分析、未执行 patch 生成与评测迭代」和启动按钮，去掉大面积橙色底色与粗体警告，使用现有 `--border` / `--bg-panel` / `--text-dim` token。
- 长对象名：标题区允许换行，`target-chip` 使用 `max-width: 100%`、`overflow-wrap: anywhere`，并给完整值加 `title`。
- `apps/web/src/pages/evolution/RunDetail.vue`：同步根节点 `align-content: start`，保证低内容时页头、信息卡与进度块不被剩余高度拉开；不改其字段、页签与步骤内容。
- 测试：补充 `ClusterPreview` 组件状态覆盖（preparing/running/paused/blocked/failed/interrupted/completed、零簇与多簇、长对象名、只读用户），新增浏览器几何回归，在 1366×768、1366×1080、1920×1080、390×844 断言顶部排列、短状态卡高度与间距不随视口高度变化，并保留多簇滚动与无横向溢出检查。

## 实施步骤

1. 用合成运行数据复现准备中页面的拉伸，记录计算样式、元素边界和重复文案。
2. 先补会失败的浏览器几何回归与组件状态断言，再修正对齐、合并状态区、收紧模式说明。
3. 回归运行详情低内容、仅聚类多簇、长对象名与窄屏，采集同视口前后截图。
4. 同步设计文档、Agent Note 与流程状态，运行聚焦单测、类型、lint、样式、E2E 与流程门禁。

## 依赖与交付边界

- 依赖：无阻塞依赖；关联 #669 与滚动问题 #496。
- 交付边界：只改仅聚类页与运行详情根节点的纵向布局、状态呈现、对应测试和设计说明；不改聚类算法、API、契约、状态机、评测超时或其他页面。
- 不把生产运行 ID、Session 内容或生产截图提交到仓库；Before/After 截图只放 PR 描述或本地证据。

## 独立验证

```sh
pnpm --filter @harness/web exec vitest run src/pages/evolution/ClusterPreview.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm verify:web-style
pnpm test:e2e -- --pattern cluster
pnpm verify:flow
```

- 新几何回归在修正前失败、修正后通过；1366×768 与 1366×1080 下短状态卡高度和相邻间距差 ≤2 CSS px，内容顶部与滚动容器内容盒对齐，剩余空白在内容下方。
- 准备中页面只出现一个主体状态区，文案来自 `progress.stageLabel`；多簇页面可滚动到最后一簇；390×844 下由文档滚动且无横向溢出。
- 类型、lint、样式、文档与流程门禁通过；PR 提供修复前后同视口截图和几何测量。

## 验收标准

- 同宽、同字体和缩放下，视口高度从 768 增至 1080，短状态卡高度及区块间距变化不超过 2 CSS px；剩余空白位于内容下方。
- 准备流程只有一个主体状态区，正常模式说明不使用大面积警告卡。
- 沿用详情页视觉 token，窄屏及长名称无横向溢出。
- 暂停、继续、重试、权限和启动行为不回归，多簇可滚至末尾。
- 运行详情低内容状态同样顶部排列；PR 提供同视口前后截图和几何断言。

## 门禁与 CI

- 聚焦组件测试和浏览器几何回归纳入现有 CI；运行前端单测、类型、lint、样式、文档与流程门禁，覆盖率不低于 80%。

## 非目标

- 不改聚类算法、API、状态机和评测超时。
- 不以固定卡片高度、全局缩放、装饰或隐藏必要信息掩盖问题。
- 不重排运行详情的字段、页签与步骤内容，不改全局壳层。
