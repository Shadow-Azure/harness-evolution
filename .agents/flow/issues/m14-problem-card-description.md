# Session 页问题列表卡按原型显示问题描述与证据

[English](m14-problem-card-description.en.md) | 中文

```yaml flow
kind: issue
id: m14-01
milestone: m14
depends: []
priority: P1
status: in-progress
scope:
  - apps/web/**
  - tests/e2e/**
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr:
  - ../../notes/implemented/feature/2026-11-18-problem-card-description.md
github:
  number: 371
  url: https://github.com/Shadow-Azure/harness-evolution/issues/371
```

## 背景

[#370](https://github.com/Shadow-Azure/harness-evolution/issues/370) 记录：生产 Session 错误查看页（`/workspaces/{wid}/sessions/{sid}`）右下角「问题」列表卡把第二行换成了归因摘要，未分析 case 固定显示「尚未完成归因分析」，类型徽章、完整 case ID 与「关联：…」行也缺失；V2 原型 `FindingList` 在同一位置以问题描述为主体，并带 `self` / `discovery` 类型徽章、对象徽章、完整 case ID、facts、「关联：…」和「定位 ↗」。

`BadCaseList` 非 compact 模板此前把 `badCaseSummary(problem)` 当作正文，`badCaseSummary` 对 `unanalyzed` 返回固定文案、对已分析 case 返回归因 `summary` / `reason`，于是列表卡永远看不到 `reason` 描述正文；同时 ID 只显示前 8 位，`badCaseSummary` 也是该模板唯一的消费方。

## 结论

列表卡信息层级以 V2 原型为准：第二行显示 `problem.reason`（描述正文），保留轻量的归因状态胶囊，并补类型徽章、对象徽章、完整 case ID 与「关联：…」行；归因摘要不再进入列表卡。理由是原型在 `FindingList` 中明确以描述为主体，而 #370 的目标是让未分析 case 也能在会话页读到问题现象，不必先进入错误详情页。

## 目标

- 未分析与已分析 case 的会话页列表卡都显示 `reason` 描述正文，Markdown 安全渲染。
- 卡片补 `badCaseType`（`self` / `discovery`）徽章、`objectName` 徽章、完整 `badCaseId`（保留深链）与「关联：`objectType` · `objectName`」行。
- 归因状态保留轻量胶囊，`degraded` 标记照旧可见。
- 整卡点击仍然定位到执行流，描述里的链接仍然可点。
- V2 原型的 `FindingList` 与生产实现同构：描述按同一 Markdown 约定渲染。

## 设计依据

- [V2 原型 Session 页 BAD CASE 列表](../../../plans/ui-prototype-v2/harness-evolution.html)：`FindingList` 渲染 BC 编号、标题、类型/对象、完整 case ID、问题描述、facts、关联、`定位 ↗`。
- [V2 原型 FindingDescription](../../../plans/ui-prototype-v2/harness-evolution.html)：未归因 case 仍渲染描述，只在头部加「尚未归因」；描述按 Markdown 渲染。
- [08 §3.4 问题列表联动 / §5 Session 概览](../../../plans/fullstack-design/08-frontend-implementation.md)：列表卡的信息层级、整卡定位与 Markdown 约定。
- [05 §9 bad case DTO](../../../plans/fullstack-design/05-api-design.md) 与 [06 §4.1 bad_cases](../../../plans/fullstack-design/06-database-design.md)：`reason` 是描述正文，`badCaseType` 由 `bad_case_type` 映射。
- [2026-10-29 bad case title Agent Note](../../notes/implemented/feature/2026-10-29-bad-case-title.md)：错误详情页按「短标题 + 描述正文」两级渲染，列表卡主文本为 `title`。

## 实现内容

- `apps/web/src/components/bad-cases/BadCaseList.vue` 非 compact 模板重排为「BC 编号 + 卡片正文 + 定位」：头部依次渲染标题、`type-badge`、`object-badge`、完整 `problem-id` 深链、状态胶囊与 `degraded` 标记；正文用 `renderMarkdown(problem.reason, { images: false })` 渲染，带 `.problem-detail.markdown` 紧凑排版；facts 改为与原型和错误详情页一致的 key/value 双列 chip，随后是 `关联：objectType · objectName`；行尾 `定位 ↗`。
- 整卡交互沿用 compact 模板的覆盖按钮模式：正文 `pointer-events: none`、链接提升到按钮之上，既有单卡选中语义与 `aria-pressed` 不变，描述里的 Markdown 链接不会触发选中。
- `badCaseDisplay.ts` 删除已无消费方的 `badCaseSummary` 与 `badCaseFacts` 拼接层（卡片改用 `badCaseFactEntries` 渲染 key/value）；`badCaseFactEntries` / `badCaseState` 不变。
- 类型徽章沿用错误详情页的 token 映射（`self` 紫、`discovery` 蓝），以页面间一致优先；原型样式表里两者相反，属于原型自身不一致，本次不扩面统一。
- V2 原型 `FindingList` 的 `fi-detail` 改用既有 `renderMarkdown` 渲染并补 `.fi-detail.markdown` 段落/列表/行内代码/代码块样式，与生产同一约定。
- 单测覆盖 BC 编号、类型/对象徽章、完整 ID 与 aria、描述正文、Markdown 列表与行内代码、外链属性、原始 HTML 转义、图片降级、facts 与关联行；E2E 断言四个 fixture 会话的卡片正文、徽章、完整 ID、关联行与 F2P/P2P 列表。

## 实施步骤

1. 先补 `BadCaseList.test.ts` 的失败用例：未分析卡显示描述、完整 ID、类型/对象徽章、关联行，Markdown 列表与行内代码按预期渲染。
2. 重排非 compact 模板与样式，接入 `renderMarkdown` 并删除 `badCaseSummary`。
3. 更新 `m4-problem-cards` E2E：从卡片而不是按钮读文本，补四个 fixture 会话的卡片内容断言。
4. 同步 `08 §3.4` 与 V2 原型 `FindingList`，新增 Agent Note 记录「以原型为准」「为什么删摘要」「覆盖按钮与链接取舍」。
5. 用 1440px 同视口、同一 fixture 场景重拍 Before/After，并与原型截图对照；差异回修。

## 依赖与交付边界

- 依赖：无新增依赖；#363 的 Markdown 渲染能力（`utils/markdown.ts`）已合并，`BadCase` 契约已有 `badCaseType`、`reason`、`objectName`、`objectType`、`metaData`。
- 交付边界：只改 Session 页问题列表卡及其测试、原型、`08`、Note 与证据；不改错误详情页、接口、数据模型、归因逻辑与列表之外的页面。
- 不把生产 Session 或描述内容写入仓库 fixtures；证据截图只作为 PR 附件。

## 独立验证

```sh
pnpm --filter @harness/web test -- src/components/bad-cases/BadCaseList.test.ts src/components/bad-cases/badCaseDisplay.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "m4 problem cards"
pnpm lint:docs
```

- 预期：单测覆盖未分析与已分析 case 的卡片正文、完整 ID、徽章、关联行与 Markdown 安全渲染；E2E 断言会话页卡片显示问题描述（含 F2P/P2P 列表）且错误详情页不回归；文档门禁通过。
- 人工验证：在 1440px 下打开会话页问题列表，确认描述、徽章、完整 ID、关联与定位可见，并与原型截图对照。

## 验收标准

- 未分析 case 的会话页列表卡显示问题描述，带 BC 编号、类型/对象徽章、完整 case ID、关联行与「定位 ↗」。
- 已分析 case 的归因摘要不覆盖描述；状态胶囊与 `degraded` 标记仍在。
- 描述按 Markdown 安全渲染：原始 HTML 不生成节点、外链加固、图片降级；纯文本描述不回归。
- 错误详情页的描述渲染与 #363 行为不变。
- V2 原型 `FindingList` 与生产同构；PR 含刷新后的 Before/After 对比截图。

## 门禁与 CI

- `pnpm --filter @harness/web test -- src/components/bad-cases/BadCaseList.test.ts src/components/bad-cases/badCaseDisplay.test.ts`
- `pnpm typecheck:web`、`pnpm lint:web`、`pnpm test:e2e -- "m4 problem cards"`
- `pnpm verify:flow`、`pnpm test:gates`、`pnpm lint:docs`
- PR 标题与提交信息含 `(#371)`，检视按 `docs/review.md`。

## 非目标

- 不重做问题列表的信息架构，不改归因状态机、数据模型或 API。
- 不改错误详情页的问题描述与归因展示，不改执行流图问题卡。
- 不新增 Markdown 渲染库，不改变 `renderMarkdown` 的安全配置。
- 不调整其余页面配色或排版。
