# Agent Note: 仅聚类页复用 V2 簇卡并收回聚类步骤口径

Status: implemented

[English](2026-11-21-cluster-preview-results.en.md) | 中文

## Problem

仅聚类 run 的核心产出已经由 `GET /runs/{rid}/steps/clusters` 返回，但 `ClusterPreview.vue` 自 m5-05 起只渲染 banner、运行标题、状态条和对象/时间窗，页面因此整页空白；同时 `_progress()` 对所有 mode 使用完整七步的 `total_units()` 与七步标签，完成态 `unit=5` 被说成「第 6/7 步 · 迭代优化」，与 `state.py` 对 `cluster_only` 隐藏 `iteration/final` 的规则自相矛盾。[issue #466](https://github.com/Shadow-Azure/harness-evolution/issues/466) 记录了生产截图、同构复现与根因。

这里的真正张力是产品方向：V2 原型没有仅聚类页，也没有向导里的「仅聚类」出口，看起来可以删除入口；但功能清单 [02 F12](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/02-features.md) 与 [08 §11](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#11-仅聚类页pagesevolutionclusterpreviewvue) 仍把该页定义为正式能力，V1 基线原型也有完整页面。生产同时保留了入口、路由与 `cluster-previews` 接口，删除会缩小已承诺的能力。

## Decision

- 保留 `cluster_only` 能力，按 08 §11 / V1 基线补全页面：输入概况、按严重程度降序的簇列表、可展开来源 bad case、banner 内的「以这批问题启动自进化 →」。视觉不另造语言，直接复用 V2 运行详情第 5 步的簇卡与 banner 样式；`StepClusters.vue` 增加可选的标题/副标题 props，默认值保持运行详情不变。
- 「启动自进化」不信任前端缓存：完成后并行读取 `steps/range`、`steps/clusters` 与 `steps/attribution`，用 range 的持久条件快照（对象、版本、时间窗、policy、cache）重建 `mode=full` 请求，202 后跳到运行详情；attribution 的 `badCaseId → sessionId` 映射只用于来源 bad case 深链。这样即使 run 卡片或列表缓存过期，也不会用错条件。
- 可见进度归 `state.py` 所有：新增 `progress_total(mode, cluster_count)`，`cluster_only` 返回固定的五步；`_progress()` 用它计算 total/percent，用 /5 标签并把完成态写成「第 5/5 步 · 聚类完成」，`doneRounds=0`、`accepted=0`。完整 run 的七步口径不变。
- 列表卡片按 mode 收口：仅聚类完成卡徽标为「✓ 已完成 · 仅聚类」，用聚类数替换「已跑轮次」，底部说明未执行迭代/终评；完整 run 的卡片不变。
- 页面根节点按 bugfix-01 的约定自己承担滚动：`height: 100%; overflow-y: auto`，1500×837 下可滚到最后一个簇；≤640px 交回文档滚动。

## Alternatives considered

- **按 V2 原型删除「仅聚类」入口、路由与 `cluster-previews`**：能消除「有入口、无设计目标」的断层，但 02 F12 与 08 §11 仍把该页列为正式功能，删除会让已交付的 API、历史 `cluster_only` run 和用户入口失效；产品方向未确认前不做破坏性收缩。拒绝。
- **让 `cluster_only` 继续用七步 total，只把 unit=5 的标签改掉**：标签不再提迭代，但进度条仍按 7 格、百分比仍可能 71%，列表卡片与详情状态的口径继续不一致。拒绝；total 必须与可见步骤同源。
- **为仅聚类页新建一套簇卡组件**：页面结构不同会带来两份 rank/类型/置信度/严重度实现，下一轮样式调整必然漂移；现有 `StepClusters` 已覆盖所需字段。拒绝，改用可选标题 props。
- **从 run 卡片字段直接拼启动条件**：卡片只有 policy preset，没有自定义开关，`mode=full` 会静默使用不同策略；range step 才是持久条件快照。拒绝。

## Consequences

- 仅聚类完成态的详情页显示「第 5/5 步 · 聚类完成」，列表卡片显示「✓ 已完成 · 仅聚类」且不再出现「已跑轮次」或终评缺失；`GET /runs/{rid}` 的 `progress.total` 对 `cluster_only` 为 5。
- 运行详情对 `cluster_only` 仍返回七个 step 节点（迭代/终评为 pending），因为七步 key 是共享契约；该 run 的详情页不是本次入口，页面不会渲染这些 pending 节点。
- V2 原型仍没有仅聚类页：本页结构以 08 §11 / V1 基线为准，视觉以 V2 第 5 步为准。若未来原型补页面，应与本页对齐，而不是反过来删生产能力。
- 页面新增自己的滚动容器，后续 workspace shell 若改变滚动约定，`ClusterPreview` 与 `RunDetail` 需要一起调整。
- 回归由 `ClusterPreview.test.ts`（准备态不拉 clusters、完成态渲染概况/簇卡/来源表、启动 body 与跳转、失败态）和 m11-05 E2E（真实浏览器断言簇卡、输入概况、启动按钮、状态不含迭代）锁定；空壳页面不能再全绿。
