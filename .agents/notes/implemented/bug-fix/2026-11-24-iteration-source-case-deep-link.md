# Agent Note: 第 5、6 步来源 bad case 接回错误详情深链

Status: implemented

[English](2026-11-24-iteration-source-case-deep-link.en.md) | 中文

## Problem

运行详情第 5 步的簇内来源表和第 6 步的轮次来源表复用 `StepCaseTable`。该组件只有在同时拿到 `wid` 与 `caseSessions[badCaseId]` 时才渲染 `<a>`，否则静默走纯文本分支；这正是生产上「来源 bad case」ID 不可点击、键盘也无法聚焦的原因。

映射原料一直存在：运行详情已为信息面板读取 `steps/attribution`，其 `payload.rows[]` 同时带 `badCaseId` 与 `sessionId`。但页面没有像 `ClusterPreview.vue` 那样把 rows 折成映射，`RunStepContent` 也没有向下传；`StepIterations` 甚至没有 `caseSessions` prop，连 `wid` 都没交给表格。结果是只有「仅聚类」预览页的同一张表可点，运行详情第 5、6 步同根因失效。

测试没有锁住接线：`StepContent.test.ts` 直接挂载 `StepCaseTable` 或只测簇高亮，没有用例挂载 `RunDetail` 断言第 5、6 步的锚点，因此该回归可以全绿。

## Decision

- `RunDetail.vue` 从已加载的 `attributionData.payload.rows` 计算 `caseSessions: Record<string, string>`，与 `ClusterPreview.vue` 共用 `runDetail.ts` 的 `caseSessionMap()`（同一 case 保留首个 Session）；这是页面并行读取归因结果的既定数据来源，见 `08 §11`。
- `RunStepContent.vue` 新增 `caseSessions` prop 并向下传给 `StepClusters` 与 `StepIterations`；`StepIterations.vue` 新增同名 prop，并把 `wid` 与映射一起交给 `StepCaseTable`。
- `StepCaseTable.vue` 的链接分支补 `target="_blank"` 与 `rel="noopener noreferrer"`，并补完整 ID 的 `title`、`来源问题 …，在新窗口打开问题描述` 的 `aria-label` 与 `:focus-visible` 轮廓；样式对齐 V2 原型 `.idlink`（等宽、蓝色、虚线下划线、指针、悬停变实线）。深链复用 `badCaseDeepLink()`，`?case=&tab=attr` 规则不变。无映射时仍退化为带 `title` 的纯文本（降到 `--text-dim`），不渲染空 `href`。
- 回归覆盖分层：`StepContent.test.ts` 分别挂载第 5、6 步断言锚点的 Session、`case`、`tab=attr`、`target` 与无映射回退；`RunDetail.test.ts` 断言页面把归因映射接到两步；`m10-06` E2E 用现有 fixture 的已展开簇与已完成轮次断言真实 DOM 锚点。
- `08 §10.3` 补一句「第 6 步来源 bad case ID 可深链错误详情」，与第 5 步和 `§11` 的既有描述对齐。

## Alternatives considered

- **在 `steps/clusters` / `steps/iteration` 契约里加 Session 字段**：拒绝。`08 §11` 已明确选择页面读取 `steps/attribution` 得到映射，加字段会扩大 API 与契约变更面，且与仅聚类页的既有实现分叉。
- **让 `StepCaseTable` 自己请求归因数据**：拒绝。展示组件会耦合网络与查询缓存，同一张表在仅聚类页、第 5 步、第 6 步会重复请求，也让「无映射回退文本」的边界消失。
- **逐行按 `badCaseId` 查询 Session**：拒绝。N 条来源就是 N 次请求，而归因响应已经一次性带齐所需字段。
- **只加样式让文本看起来可点**：拒绝。没有锚点和 `href` 仍然无法新窗口打开、无法键盘聚焦，也没有真实深链。
- **同时改写第 5 步的 `cb-label` 文案**：本 issue 不做。文案属于非目标范围，先恢复真实链接；标签文案与原型的一致性另案处理。

## Consequences

- 第 5、6 步来源表在归因步骤可读时渲染真实深链，点击在新窗口打开该行 bad case 的错误详情；不同 Session 的 case 落到各自 Session，不会串行。
- 映射依赖 `steps/attribution` 已加载且该步骤 `clickable`。归因不可达或该 case 不在归因 rows 中时，表格保持纯文本并保留完整 ID 的 `title`，不出现空锚点。
- 没有 API、`packages/contracts`、聚类/迭代算法或深链页签约定的变化；仅聚类预览页共用同一组件，来源 ID 也随之改为新窗口打开，与原型一致。
- 组件、页面与 E2E 三层测试锁住接线，后续再改 `StepCaseTable` 的 props 或页面下传链时会先红。
