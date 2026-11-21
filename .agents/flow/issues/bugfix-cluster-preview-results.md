# 仅聚类页只有壳：补聚类结果、输入概况与状态口径

[English](bugfix-cluster-preview-results.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-10
milestone: bugfix
depends:
  - m10-04
  - m10-05
priority: P2
status: ready
scope:
  - apps/api/**
  - apps/web/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 468
  url: https://github.com/Shadow-Azure/harness-evolution/issues/468
```

## 背景

[issue #466](https://github.com/Shadow-Azure/harness-evolution/issues/466) 记录了生产「自进化 → 仅聚类」run 详情页只有一条 banner、运行标题、状态条和「进化对象 / 时间窗口」，下方整页空白；状态条还显示 `completed` 与 `第 6/7 步 · 迭代优化 · 第 1/1 轮`。同一 run 的 `GET /runs/{runId}/steps/clusters` 已返回 1 个含 rank、标题、category、caseCount、confidence、severity 的簇，但页面从不请求它。根因是 `apps/web/src/pages/evolution/ClusterPreview.vue` 自 m5-05 起一直是占位壳，没有输入概况、cluster 列表和启动按钮；`apps/api/app/service/evolution/runs.py` 的 `_progress()` 对所有 mode 固定按七步计算，`cluster_only` 完成时 `unit=5` 落入迭代标签与 71% 进度。

V2 原型 `plans/ui-prototype-v2/harness-evolution.html` 没有独立的仅聚类页，聚类展示在运行详情第 5 步；独立的「问题聚类结果」页定义在 V1 基线原型与 [08 §11](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#11-仅聚类页pagesevolutionclusterpreviewvue)。本 issue 保留现有入口与 `cluster_only` 能力，按 08 §11 / V1 基线补齐页面，并让 V2 的簇卡与 banner 样式成为视觉来源。

## 目标

- 仅聚类 run 完成后，页面请求并渲染 `steps/clusters`：输入概况（关联 Session / 问题报告 / 潜在 bad case / 聚类数）、按严重程度降序的簇列表、可展开的来源 bad case 表，视觉复用 V2 运行详情第 5 步的簇卡。
- `preparing` / `running` 期间展示准备阶段与轮询，不在未完成时请求 cluster 步骤；失败与空簇有明确状态。
- banner 提供「以这批问题启动自进化 →」，用该 run 的同一条件（对象、版本、时间窗、潜在策略、缓存开关）创建 `mode=full` run 并跳转运行详情。
- 后端 `_progress()` 区分 `cluster_only`：总步数 5、阶段标签落在「聚类与严重度」，完成态文案为「聚类完成」，不再出现迭代轮次或 71% 进度；列表卡片同步。
- 单元测试与 E2E 锁定「页面确实渲染聚类内容与启动按钮」以及「仅聚类完成态不显示迭代」，避免空壳再次全绿。

## 设计依据

- [08 §11 仅聚类页](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#11-仅聚类页pagesevolutionclusterpreviewvue)：preparing 轮询、banner + 启动入口、输入概况、聚类列表与来源 bad case、`steps/clusters` 数据通道。
- [02 F12](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/02-features.md)：仅聚类结果页的功能边界与数据来源。
- [05 §4.12](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/05-api-design.md)：`cluster-previews` 启动与 `steps/clusters` 契约；本 issue 不改契约。
- [V1 基线原型 renderClusterOnly()](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/14-15-ui-prototype/harness-evolution.html#L3242)：标题、输入概况、簇卡与启动按钮的页面结构。
- [V2 原型运行详情第 5 步](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L5423)：簇卡、统计条与 banner 样式；V2 没有独立仅聚类页，本页不另造视觉语言。
- [issue #466](https://github.com/Shadow-Azure/harness-evolution/issues/466)：生产复现、截图对照与根因。

## 实现内容

- `apps/web/src/pages/evolution/ClusterPreview.vue`：
  - 页头改为「问题聚类结果」+ 对象 chip；保留返回列表按钮。
  - banner 文案明确「未执行 patch 生成与评测迭代」，右侧放「以这批问题启动自进化 →」；启动中禁用并显示失败原因。
  - 完成后并行读取 `steps/range`（取同一条件）与 `steps/clusters`；输入概况用 run stats 的 sessions / badCases / potential / clusters，条件行用 range 的 window、models 与 policy。
  - 簇列表复用 `components/StepClusters.vue`，给组件增加可选的标题/副标题 props，默认值保持运行详情第 5 步不变。
  - 状态徽标使用中文文案；完成态展示 `progress.stageLabel`（后端修正后为聚类完成），preparing 时展示「正在关联 Session / 筛选潜在 / 生成归因 / 聚类」。
  - 「启动自进化」调用 `startEvolutionRun`，body 由 range condition 还原 target / window / policy / cache，`mode: "full"`，202 后跳到 `/evolution/runs/{runId}`。
- `apps/api/app/service/evolution/runs.py`：`_progress()` 对 `cluster_only` 使用 `PREPARE_COMPLETE_UNIT` 作为总步数，阶段标签使用 /5 文案，完成态为「第 5/5 步 · 聚类完成」，`doneRounds` 为 0；完整 run 的七步口径不变。
- `apps/web/src/pages/evolution/components/RunCard.vue`：仅聚类完成卡的徽标改为「✓ 已完成 · 仅聚类」，用「聚类」替换「已跑轮次」，底部改为「仅聚类分析 · 未执行 patch 生成与评测迭代」，不再显示「终评数据暂不可用」。
- 测试：
  - `apps/api/tests/m5-04-run-list/test_runs_service.py` 增加 `cluster_only` 的进度参数化用例；`m5-01-evolution-state` 增加 `progress_total()` 用例。
  - `apps/web/src/pages/evolution/ClusterPreview.test.ts` 覆盖准备态不请求 clusters、完成态渲染输入概况/簇卡/来源表/深链、启动 full run 的请求 body 与跳转、失败态；`RunCard.test.ts` 覆盖仅聚类完成卡。
  - `tests/e2e/m11-05-v2-cross-stack.test.mjs` 的仅聚类段补断言：`.cluster` 数量、输入概况、聚类标题、启动按钮、来源深链、状态文案不含迭代，以及列表卡片徽标与「已跑轮次」不再出现。
- 新增一条 `bug-fix` Agent Note，记录「保留 cluster_only 能力并复用 V2 簇卡」的取舍，以及为什么没有按 V2 原型删除入口。

## 实施步骤

1. 修正后端 `_progress()` 的 `cluster_only` 口径并补 API 单测。
2. 扩展 `StepClusters.vue` 的可选标题 props，保持运行详情默认渲染不变。
3. 实现 `ClusterPreview.vue` 的准备态、输入概况、簇列表、启动 full run 与错误态。
4. 补 Web 单测与 m11-05 E2E 断言，更新受影响的既有断言。
5. 起 fixtures + API + Web 的本地同构页面，截取 Before（当前 main）与 After（本分支）同视口证据，对照 V1 基线 / V2 第 5 步与 08 §11。
6. 写 Agent Note，运行聚焦测试、类型检查、lint、文档与流程门禁，提交 PR。

## 依赖与交付边界

- 依赖：m10-04、m10-05（七步准备与四步向导 / cluster-previews 已落地）。
- 交付边界：只改仅聚类页、其依赖的簇卡标题 props、run 进度投影与对应测试；不改聚类算法、置信度/严重度算法、`steps/clusters` 契约、run 状态机、历史 run 数据，也不改启动向导与运行详情的既有布局。
- V2 原型没有独立仅聚类页，本页结构以 08 §11 / V1 基线为准、视觉复用 V2 第 5 步簇卡；不因本 issue 删除「仅聚类」入口。
- 不把生产运行 ID、Session 内容、生产截图或凭据写入仓库；Before/After 与冒烟截图只放 PR 描述或本地证据。

## 独立验证

```sh
apps/api/.venv/bin/python -m pytest apps/api/tests/m5-04-run-list/test_runs_service.py
pnpm test:web -- ClusterPreview
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- --pattern m11-05
pnpm verify:flow && pnpm verify:docs
```

- `cluster_only` run 的卡片刻度：`progress.total=5`，unit=5 时 `percent=100`、`stageLabel="第 5/5 步 · 聚类完成"`、`doneRounds=0`；完整 run 的原有用例继续通过。
- 完成态页面：`[data-testid='evolution-cluster-preview']` 内出现「问题聚类结果」「输入概况」「聚类出的 N 类问题」「以这批问题启动自进化」，`.cluster` 数量等于接口返回的簇数；展开后出现来源 bad case 表。
- preparing 态只轮询 run detail，不请求 `steps/clusters`；完成后才发出该请求。
- 点击启动按钮发出 `POST …/evolution/runs`，body 的 target、window、policy、cacheEnabled 与 range condition 一致且 `mode="full"`，随后进入 `/evolution/runs/{runId}`。
- 状态条不再出现「迭代」「第 6/7」或 71%。

## 验收标准

- 仅聚类页在 1500×837 视口下展示完整聚类内容：banner + 启动按钮、问题聚类结果标题与对象 chip、输入概况、按严重度降序的簇列表、可展开的来源 bad case；页面可滚动到最后一个簇。
- 状态徽标与阶段文案为中文；完成态显示「第 5/5 步 · 聚类完成」，列表卡片与详情页一致，均不再把仅聚类说成迭代步骤。
- 「以这批问题启动自进化」可以用同一条件创建完整 run 并进入运行详情；失败时在页面内给出可读错误。
- V2 运行详情第 5 步的簇卡标题、当前步骤渲染与既有 E2E 断言不回退。
- PR 附同场景、同视口、同主题的 Before/After 截图（Before 标注基线提交），并附与 V1 基线 / V2 第 5 步的对照说明；不提交生产截图到仓库。
- 最终验收由提出人确认；修复 PR 只交付可复核的实现与证据。

## 门禁与 CI

- API 单测：`apps/api/.venv/bin/python -m pytest apps/api/tests/m5-04-run-list/test_runs_service.py`；全量 `pnpm test:api` 由 CI 执行。
- Web：`pnpm test:web -- ClusterPreview`、`pnpm typecheck:web`、`pnpm lint:web`。
- E2E：`pnpm test:e2e -- --pattern m11-05`。
- 流程与文档：`pnpm verify:flow`、`pnpm lint:docs`；PR 标题带 `(#<本 issue 编号>)` 并在正文引用 #466。
- CI 全绿后交付人工检视；本 PR 由人合并。

## 非目标

- 不删除「仅聚类」入口、`cluster-previews` 接口或 `evolution/cluster/:runId` 路由，也不把 `cluster_only` run 统一改导到运行详情第 5 步。
- 不改聚类输入、置信度/严重度算法、归因缓存、`steps/clusters` 响应字段或历史 run 迁移。
- 不重构启动向导、运行列表、运行详情与全局样式；不新增设计 token 或第二套簇卡组件。
- 不补齐 V2 原型的仅聚类入口与页面（原型本身没有该页），也不修改 `plans/ui-prototype-v2/harness-evolution.html`。
