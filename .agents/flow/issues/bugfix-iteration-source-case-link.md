# 运行详情第 6 步「来源 bad case」ID 不可点击，未跳转错误详情

[English](bugfix-iteration-source-case-link.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-48
milestone: bugfix
depends:
  - m21-01
priority: P2
status: in-progress
scope:
  - apps/web/**
  - tests/e2e/**
  - plans/fullstack-design/**
  - .agents/**
adr: []
github:
  number: 569
  url: https://github.com/Shadow-Azure/harness-evolution/issues/569
```

## 背景

### 问题场景

2026-11-24 在生产「自进化 → 运行详情」第 6 步「迭代优化」中，用户展开 #1 轮次（12 个来源 bad case）后，红框标出的 bad case ID 全部是纯文本：`swe-12a7bc0ee36f3dc94a22`、`swe-1444a4e1d1e064e1570a`、`swe-1969b8b81bb2e989e027` 等。ID 是普通文本，悬停没有指针与下划线，点击后浏览器地址与页面内容都不变。用户预期与 V2 原型一致：点 ID 跳到该 bad case 的错误详情。

生产现场（红框为用户标注的不可点击区域）：

![生产第 6 步：来源 bad case ID 为纯文本](https://github.com/Shadow-Azure/harness-evolution/releases/download/iteration-source-case-link-evidence-20261124/prod-step6-iteration-badcase-ids.jpg)

复现路径：生产「自进化」→ 历史记录 → 任一已进入第 6 步的运行 → 运行详情 → 第 6 步「迭代优化」→ 展开任一轮次 → 点击「来源 bad case」表第一列 ID。第 5 步「归因聚类与严重度排序」的簇内来源表复用同一个组件，同样不可点击。

### 现场观察

- 第 1 轮表头为「来源 bad case（12 个 · 由归因结论聚类而来）」，12 行 ID 全部是文本节点，表格内 `a` 数量为 0。
- ID 单元格没有锚点、`cursor` 为 `auto`、`tabIndex` 为 `-1`，键盘无法聚焦。
- 第 5 步的簇内来源表同样没有锚点；只有「仅聚类」预览页（`ClusterPreview.vue`）的同一张表能点。

### V2 原型对照

原型 `plans/ui-prototype-v2/harness-evolution.html#L5453-L5461` 的 `evCaseTable()` 对第一列统一调用 `evCaseLink()`；`evCaseLink()`（`#L5187-L5189`）输出 `<a class="idlink" target="_blank" rel="noopener">`，默认打开错误详情。`.idlink`（`#L543`）有 `cursor: pointer` 与蓝色虚线下划线，和普通文本可区分。第 5 步簇卡标签写明「来源 bad case（N 个 · 点 ID 跳到错误详情）」（`#L5577`）；第 6 步轮次卡复用同一张 `evCaseTable`（`#L5546`），所以原型里第 6 步的来源 ID 同样可点。

V2 原型同位置（第 5/6 步共用的来源 bad case 表，1500×950 视口，本地 demo run `EV-20261106-02`）：

![V2 原型：来源 bad case ID 为可点击链接](https://github.com/Shadow-Azure/harness-evolution/releases/download/iteration-source-case-link-evidence-20261124/proto-step6.png)

原型第 5 步的提示语与链接样式（同一组件）：

![V2 原型第 5 步：点 ID 跳到错误详情](https://github.com/Shadow-Azure/harness-evolution/releases/download/iteration-source-case-link-evidence-20261124/proto-step5.png)

两张图的目标 run 与生产不同（原型用自带演示数据），对照的是同一页面位置、同一张表的交互与信息结构。

### 根因分析

结论：**运行详情页没有把第 4 步归因行里的 `badCaseId → sessionId` 映射接到共用的 `StepCaseTable`，链接分支永远拿不到 Session，组件静默退化为纯文本；第 5、6 步同因。**

1. `StepCaseTable` 只有在 `wid` 与 `caseSessions[badCaseId]` 同时存在时才渲染 `<a>`；否则走 `v-else` 文本分支（`apps/web/src/pages/evolution/components/StepCaseTable.vue#L26-L32`、`#L57-L68`）。文本分支没有锚点语义，点击无反应。
2. 第 6 步没有传映射：`StepIterations.vue#L213` 只写 `<StepCaseTable :cases="round.cases" />`，组件 props（`#L10-L14`）没有 `caseSessions`；`RunStepContent.vue#L75-L80` 也没有向它传。第 5 步的 `StepClusters.vue` 虽然声明并下传了 `caseSessions`（`#L13`、`#L191-L194`），但运行详情里的 `RunStepContent.vue#L68-L74` 没有传值，所以同样为空。
3. 运行详情页本来就有映射原料：`RunDetail.vue` 已按 `attributionStep.clickable` 读取 `steps/attribution`（`#L199-L205`），但没有像 `ClusterPreview.vue#L70-L76` 那样把 `payload.rows` 折成 `badCaseId → sessionId`，也没有把结果向下传（`RunDetail.vue#L956-L967`）。`ClusterPreview.vue#L330` 传了 `:case-sessions`，所以只有「仅聚类」预览页的链接是通的，运行详情页缺同一段接线。
4. 契约侧不需要新增字段：生产 `steps/iteration` 实测 12 条来源项只有 `badCaseId/title/objectName/badCaseType/triggerAt/createdAt`，没有 Session；`plans/fullstack-design/08-frontend-implementation.md#L870` 已明确选择「页面并行读取 `steps/attribution` 得到 `badCaseId → sessionId` 映射，不在 `steps/clusters` 契约里新增 session 字段」。缺的是页面接线，不是 API。
5. 测试没有覆盖这段接线：`StepContent.test.ts#L482` 只直接挂载 `StepCaseTable`，`StepClusters` 的用例只测高亮与空表；没有用例挂载 `RunStepContent`/`RunDetail` 并断言第 5、6 步来源表的锚点，所以该回归可以全绿。

影响：第 6 步（以及同样使用该表的第 5 步）唯一的下钻入口失效，用户无法从迭代轮次回到来源 bad case 的错误详情核对现场；表头明确写着「由归因结论聚类而来」，却无法核对结论来源。

## 目标

- 第 6 步「来源 bad case」表的 ID 变为可点击链接：新窗口打开该行 bad case 的错误详情，Session、case 与当前行一致。
- 第 5 步簇卡来源表使用同一接线恢复链接，避免同根因只修一半。
- 链接沿用 `StepCaseTable` 现有的深链规则（`?case=<id>&tab=attr`），不新增第二套跳转约定。
- 用组件测试锁住「第 5、6 步都有锚点且 href 带对应 Session」；不引入 API/契约变更。

## 设计依据

- [08 §10.3 Step6 迭代卡](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L834)：展开内容顺序为来源 bad case → patch → candidate → 推送 → 评测 → 最终 commit。
- [08 §10 第 5 步](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L808)：簇内来源 bad case 表「ID 可深链错误详情」。
- [08 §11 簇深链数据来源](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L870)：来源 bad case 的深链由页面读取 `steps/attribution` 得到 `badCaseId → sessionId`，不在契约新增 session 字段。
- [V2 原型 `evCaseLink`](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L5187-L5189) 与 [`evCaseTable`](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L5453-L5461)：第一列是 `<a class="idlink" target="_blank">`。
- [m21-01 运行详情重排](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/flow/issues/m21-run-detail-prototype-alignment.md)：第 5、6 步沿用原型结构；本 issue 只补链接接线。

## 实现内容

- `RunDetail.vue`：从已加载的 `attributionData.payload.rows` 计算 `caseSessions: Record<string, string>`（`badCaseId → sessionId`），传给 `RunStepContent`；写法与 `ClusterPreview.vue#L70-L76` 一致。
- `RunStepContent.vue`：新增 `caseSessions` prop，向下传给 `StepClusters` 与 `StepIterations`。
- `StepIterations.vue`：新增 `caseSessions` prop，用 `:case-sessions="caseSessions"` 传给 `StepCaseTable`。
- `StepCaseTable.vue`：链接分支补 `target="_blank"` 与 `rel="noopener noreferrer"`，与 `StepPotential`、`StepAttribution` 和原型一致；`caseLink()` 的 `?case=&tab=attr` 不改。无映射时仍退化为文本（保留 `title`）。
- 测试：在 `StepContent.test.ts` 增加 `StepIterations` 挂载用例，断言每行 `td.id a` 的 `href` 含正确 Session、`case`、`tab=attr` 与 `target="_blank"`；在 `RunDetail` 相关测试中断言第 5、6 步都拿到映射。E2E 若现有 `m10-06` fixture 有已完成轮次，补一条第 6 步锚点断言。
- 文档：在 08 §10.3 补一句「来源 bad case ID 可深链错误详情」，避免下一次按纯文本实现。

## 实施步骤

1. 在 `RunDetail.vue` 计算映射并传给 `RunStepContent`，在 `RunStepContent.vue`/`StepIterations.vue` 逐层下传；先跑现有 `StepCaseTable` 用例确认组件行为不变。
2. 给 `StepCaseTable.vue` 链接补 `target`/`rel`，确认「仅聚类」预览页链接不回归。
3. 补 `StepContent.test.ts` 与 `RunDetail` 接线测试；若 E2E fixture 可用，补第 6 步锚点断言。
4. 更新 08 设计文档对应句子。
5. 用本地同构页面与 V2 原型做同视口截图（Before 为当前生产/main，After 为接线后），跑聚焦单测、类型检查与 lint。

## 依赖与交付边界

- 依赖：m21-01（第 5、6 步已按 V2 原型重排，表格结构稳定）。
- 交付边界：只改运行详情展示层接线、`StepCaseTable` 链接属性、对应组件/E2E 测试与 08 文档一句；不改 API、`packages/contracts`、`StepClusterCase`、聚类/迭代算法与深链页签规则。
- 不把生产运行 ID、Session 内容或截图提交进仓库；截图只放 issue/Release。

## 独立验证

```sh
pnpm --filter @harness/web exec vitest run src/pages/evolution/components/StepContent.test.ts src/pages/evolution/RunDetail.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "m10-06"
pnpm verify:flow
```

- 组件测试：第 6 步每个来源行 `td.id a` 存在，`href` 同时含该行 Session、`case=` 与 `tab=attr`，`target="_blank"`；第 5 步同样。无映射时不渲染锚点。
- 生产同构页面：1500×950 视口下第 6 步第 1 轮 12 行 ID 全部为链接，点击后新窗口打开对应错误详情；第 5 步同样。
- 第 5、6 步的统计、轮次状态、badge 与表格排版不回归。

## 验收标准

- 第 6 步「来源 bad case」表 ID 为可点链接，悬停有指针/下划线，键盘可聚焦；点击在新窗口打开该行 bad case 的错误详情。
- 同一轮次内不同 Session 的 case 落到各自 Session，不出现 404 或串行。
- 第 5 步簇卡来源表使用同一接线恢复链接。
- 无 `attribution` 可达数据时退化为文本，不渲染空 `href`。
- 组件测试、`pnpm typecheck:web`、`pnpm lint:web`、相关 E2E 与 `pnpm verify:flow` 通过。
- 最终验收由提出人确认。

## 门禁与 CI

- `pnpm test:web`（组件与覆盖率）、`pnpm typecheck:web`、`pnpm lint:web`、`pnpm test:e2e`（m10-06，如补用例）、`pnpm verify:flow`。
- 提交与 PR 标题带 `(#<本 issue 编号>)`；PR 描述附 Before/After 与 V2 原型对照截图。
- CI 全绿后交付人工检视；本 PR 由人合并。

## 非目标

- 不改 `steps/clusters` / `steps/iteration` 契约，不给 `StepClusterCase` 加 Session 字段。
- 不改深链页签约定（沿用 `StepCaseTable` 现有 `tab=attr`）。
- 不改表格列、摘要文案、聚类/严重度/轮次状态与第 1–4/7 步。
- 不把生产运行 ID、Session 内容或截图提交进仓库。
