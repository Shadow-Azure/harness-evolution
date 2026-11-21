# 运行详情第 4 步归因报告 ID 可点击跳转

[English](bugfix-attribution-report-links.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-06
milestone: bugfix
depends:
  - m21-01
priority: P2
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-20-attribution-report-link.md
github:
  number: 443
  url: https://github.com/Shadow-Azure/harness-evolution/issues/443
```

## 背景

生产运行详情第 4 步「对象归因」把「归因报告 ID」渲染成纯文本，单元格 `cursor: auto`、整张表 `a` 数量为 0，点击后 URL 与页面都不变。V2 原型 `plans/ui-prototype-v2/harness-evolution.html:5352-5353` 在同一位置用 `<a class="idlink" target="_blank">` 打开该 bad case 的错误详情并停在「归因分析」页签；同页第 3 步与错误详情页也已有按 bad case 深链的既有约定。生产与当前 `main` 的实现一致，不是旧构建或缓存问题。

直接原因在 `apps/web/src/pages/evolution/components/StepAttribution.vue`：报告 ID 与「来源 bad case」两列都是普通 `<td>`，没有锚点，也没有把 `wid` 传给组件。数据侧的前置缺口是 `StepAttributionRow`（`apps/api/app/service/evolution/stages.py`）只有 `bad_case_id` / `attribution_id`，没有 `sessionId`，而错误详情深链必须带 Session。完整现场测量、生产与原型对照截图见 [#443](https://github.com/Shadow-Azure/harness-evolution/issues/443)。

## 目标

- 第 4 步「归因报告 ID」显示为链接：新窗口打开对应 bad case 的错误详情，并选中「归因分析」页签；URL 的 `case` / `tab=attr` / `at` 与该行数据一致。
- 「来源 bad case」按同一约定打开「问题描述」页签，消除「蓝色但不可点」的文本。
- 为两列补可聚焦锚点、`title` 与 `aria-label`，保留现有统计、缓存/新增标签、置信度与表格排版。
- 用组件测试与 E2E 固化链接行为，并在设计文档记录第 4 步的点击契约。

## 设计依据

- [08 §10.1 七步展示要点](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L781)：第 4 步表格列为来源 bad case / 归因 ID / 分类 / 现象 / 结果来源 / 置信度。
- [V2 原型 `evStepAttr()`](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L5344-L5365)：来源列用 `evCaseLink`，报告 ID 用 `<a class="idlink">` 指向 `caseDeepLink(..., 'attr', ...)`，`target="_blank"`、`rel="noopener"`。
- [既有深链实现](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/web/src/utils/badCaseId.ts)：`badCaseDeepLink(wid, sessionId, badCaseId, tab, attributionId)` 生成 `/workspaces/:wid/sessions/:sid/errors?case=...&tab=...&at=...`。
- [第 3 步的对照实现](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/web/src/pages/evolution/components/StepPotential.vue#L96-L105)：来源 bad case 用 `badCaseDeepLink(..., 'desc')` 渲染为新窗口链接，并带 `aria-label` 与 `rel="noopener noreferrer"`。

## 实现内容

- 契约与 API：给 `StepAttributionRow` 增加必填 `session_id`；V2 取 `candidate.session_id`，legacy 取 `first.probe_session_id`；运行 `pnpm contract:generate` 更新 OpenAPI 与生成类型。
- `StepAttribution.vue`：新增 `wid` prop；两列都用 `badCaseDeepLink` 渲染锚点。报告 ID 带 `tab=attr`、`at=row.attributionId`；来源 bad case 带 `tab=desc`。锚点 `target="_blank"`、`rel="noopener noreferrer"`，保留完整 ID 作为可见文本与 `title`，并补 `aria-label`。
- `RunStepContent.vue`：把已有的 `wid` 传给 `StepAttribution`。
- 测试：组件测试断言两列锚点的 `href`、`target`、`rel`、`aria-label`；API 测试断言第 4 步行带正确 `session_id`；E2E 在 `m10-06` 的第 4 步断言链接数量、href 模式与可聚焦性，并保留现有统计断言。
- 文档：在 `plans/fullstack-design/08-frontend-implementation.md` 第 4 步表格说明补点击行为；新增 Agent Note 记录为什么由 API 补 `sessionId`、为什么不复用原型的全局 fixture 反查。

## 实施步骤

1. 改 `StepAttributionRow` 与两处行构造器，运行 `pnpm contract:generate`，确认前后端类型同步。
2. 改 `StepAttribution.vue` 与 `RunStepContent.vue`，沿用 `StepPotential.vue` 的链接样式与无障碍写法。
3. 更新 web 组件测试、`RunDetail.test.ts` 与 `StepContent.test.ts` 的 fixture、API 阶段测试、`m10-06` E2E。
4. 更新 08 设计文档与 Agent Note 双语三件套。
5. 在本地生产同构页面用合成 fixture 做 Before / After 截图与原型同视口对照，运行聚焦单测、类型检查、lint、E2E 与流程/文档门禁。

## 依赖与交付边界

- 依赖：m21-01（运行详情已按 V2 原型重排，第 4 步表格结构稳定）。
- 交付边界：只改第 4 步 DTO、组件、对应测试与文档；不改归因/聚类/缓存/评测算法，不改第 3 步与错误详情页的深链约定，不重排表格。
- 不把生产截图或 Session 内容提交进仓库；Before / After 证据只放 PR 描述与本地报告。
- bugfix milestone 由提出人确认后闭环；本 PR 用 `Refs #443`，不自动关闭 issue。

## 独立验证

```sh
pnpm --filter @harness/web exec vitest run src/pages/evolution/components/RunDetailConformance.test.ts src/pages/evolution/components/StepContent.test.ts src/pages/evolution/RunDetail.test.ts
pnpm --filter @harness/web exec vitest run src/utils/badCaseId.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:api -- -k "m10_04_stages"
pnpm test:e2e -- "m10-06 run detail"
pnpm verify:flow
pnpm lint:docs
```

- 组件测试：第 4 步两列各有锚点，来源链接 `href` 以 `case=...&tab=desc` 结尾，报告链接带 `tab=attr&at=<attributionId>`，`target="_blank"`、`rel="noopener noreferrer"` 且 `aria-label` 含完整 ID。
- API 测试：V2 与 legacy 的第 4 步行都返回非空 `session_id`，V2 等于候选行的 Session。
- E2E：`run-v2-completed` 第 4 步 6 行、12 个链接，报告链接的 `case` / `session` / `at` 与 fixture 对应，首个报告链接可聚焦；新增用例导航到生成的报告/来源 href，断言「归因分析」选中该行归因与「问题描述」页签。
- 生产同构页面：1500×837 下报告 ID 为蓝色链接、悬停有提示、Tab 可聚焦，点击后新窗口打开归因分析。

## 验收标准

- 生产同构页面第 4 步「归因报告 ID」显示为链接样式，悬停有提示，键盘可聚焦；点击在新窗口打开对应 bad case 的错误详情并停在「归因分析」页签。
- 「来源 bad case」按约定打开「问题描述」页签，不再出现「蓝色但不可点」的文本。
- 多归因时 URL 的 `at` 与该行 `attributionId` 一致；第 4 步统计、缓存/新增标签、置信度展示不变。
- 聚焦单测、`pnpm typecheck:web`、`pnpm lint:web`、相关 E2E、`pnpm verify:flow` 与文档门禁通过。

## 门禁与 CI

- 命中 `pnpm test:web`（组件测试与覆盖率）、`pnpm test:api`（阶段投影）、`pnpm typecheck:web`、`pnpm lint:web`、`pnpm test:e2e`（m10-06）、`pnpm contract:check`、`pnpm verify:flow`、`pnpm lint:docs` / `verify:docs`。
- 契约生成物由 `pnpm contract:generate` 产生，不手改；PR 必须包含 OpenAPI 与生成类型差异。

## 非目标

- 不改归因、聚类、缓存或评测算法，不改第 3 步及错误详情页的既有深链约定。
- 不重排第 4 步表格，不改列顺序、统计口径或 styles token。
- 不把生产截图或 Session 内容提交进仓库；证据只放 issue / Release / PR 描述。
- 不为历史缺失 Session 的数据伪造链接；legacy 行只使用真实 `probe_session_id`。
