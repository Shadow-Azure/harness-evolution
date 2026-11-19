# 自进化运行详情页与 V2 原型对齐

[English](m21-run-detail-prototype-alignment.en.md) | 中文

```yaml flow
kind: issue
id: m21-01
milestone: m21
depends:
  - m10-06
priority: P2
status: ready
scope:
  - apps/web/**
  - tests/e2e/**
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr:
  - ../../notes/implemented/feature/2026-11-19-run-detail-prototype-alignment.md
github:
  number: 405
  url: https://github.com/Shadow-Azure/harness-evolution/issues/405
```

## 背景

生产「自进化 → 运行详情」与 V2 原型在页面层级、字段集和统计口径上出现偏差：独立「工作区」卡把「流程进度」挤到第三张卡之后；「目标与输入」有原型与设计文档都没有的「模型（多选）」，缺少「工作空间」「可归因 / 非该对象」与策略 / 缓存来源徽标；页头多了创建人 · 时间；分布标题按已归因结论统计。原型自身又缺少设计文档 08 §10.2 / §10.4 要求的「执行日志」页签与「准备中」态，使同一页面无法用原型验收。完整对照与截图证据见 [GitHub #403](https://github.com/Shadow-Azure/harness-evolution/issues/403)。

## 目标

- 运行详情恢复为原型与设计文档的单列层级：页头（标题 + 状态 + 空间 badge）→ 目标与输入 → 流程进度 → 当前步骤产出。
- 「目标与输入」采用原型字段集：进化对象 / 版本 / 时间段 / 工作空间，关联 Session、时间段内 bad case、潜在 bad case、可归因 / 非该对象，并显示策略与缓存来源徽标；工作区、推送、评测信息并入该卡折叠区，分支名仍可复制。
- 分布标题与图例统一为「潜在 bad case 的归因结论分布」，含非该对象、复用缓存与本次新增拆分；底层统计口径不变。
- 保留「七步详情 / 执行日志」页签与「准备中」态，并在同一 PR 补齐 V2 原型与设计文档 08 的对应描述，消除原型缺口。
- 不改 API 契约、归因 / 聚类 / 评测算法、SSE、七步 key 与分页。

## 设计依据

- [08 §10.1 结构 / §10.2 交互 / §10.4 执行日志](../../../plans/fullstack-design/08-frontend-implementation.md)：详情页层级、infoPanel 的工作区与策略 / 缓存 chip、执行日志页签、准备中态。
- [V2 原型运行详情](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html)：`evInfoPanel()` 的字段顺序、分布标题与图例、策略 / 缓存徽标。
- [05 运行详情 DTO](../../../plans/fullstack-design/05-api-design.md)：`EvolutionRunDetail`、`EvolutionRunStats`、`EvolutionStepRange`、`EvolutionStepAttribution` 的现有字段。
- [Agent Note](../../notes/implemented/feature/2026-11-19-run-detail-prototype-alignment.md)：字段取舍、数据来源与原型补齐的决策。

## 实现内容

- `apps/web/src/pages/evolution/RunDetail.vue`：页头改为标题 + 状态 + 空间 badge（空间名来自 auth store，缺失时显示 —），移除创建人 · 时间；删除独立 `workspace-panel`，把工作区字段与本地路径收进 infoPanel 的折叠区；移除「模型（多选）」与独立「复用缓存归因」字段，补「工作空间」「可归因 / 非该对象」、策略 / 缓存徽标与「本次新增」。
- 数据来源：策略 / 缓存开关读取 range step 的 `condition.policy` / `condition.cacheEnabled`；非该对象、复用缓存与本次新增按 attribution step 的 `rows` 行级统计（`category` 为空即非该对象，`source` 区分 cached / fresh；本次新增只计可归因的 fresh 行），归因未完成时显示 `—` 并以「未归因」余量补齐分布条。两个 step 查询按 `run.steps` 的 `clickable` 与步骤页签启用，并与当前选中 step 共用 query key。
- 分布：类型条与图例以 `stats.potential` 为分母，类型段保留 error / prompt / model，另加非该对象段；图例固定「＝ 可归因 N · 复用缓存 N · 本次新增 N」。
- `plans/ui-prototype-v2/harness-evolution.html`：详情页加「七步详情 / 执行日志」页签与日志面板，页头加空间 badge，infoPanel 加工作区折叠区，新增一个准备中示例运行与对应状态样式。
- `plans/fullstack-design/08-frontend-implementation.md`：§10.1 补充分布口径、工作区折叠与空间 badge；§10.4 明确页签形态。

## 实施步骤

1. 按原型重排 `RunDetail.vue` 的页头、infoPanel、工作区折叠区与流程进度顺序，并接入 range / attribution step 数据。
2. 更新 `RunDetail.test.ts`：覆盖字段集、工作区位置、策略 / 缓存徽章、分布文案、页签保留与准备中态；同步调整额外 step 查询影响的请求断言。
3. 更新 `tests/e2e/m10-06-run-detail-v2.test.mjs`：断言页头空间 badge、目标与输入字段、流程进度顺序、工作区不独立成卡与执行日志页签。
4. 补齐 V2 原型的页签、日志面板、空间 badge、工作区折叠区与准备中示例，并更新设计文档 08。
5. 运行聚焦单测、类型检查、E2E 与文档 / 流程门禁；生成 Before / After 截图放入 PR 描述。

## 依赖与交付边界

- 依赖：m10-06（七步运行详情与执行日志已落地）。
- 非目标：不改 `apps/api/**`、`packages/contracts/**`、归因 / 聚类 / 评测算法、SSE、七步 key 与分页；不改步骤内容组件；不把生产截图内容提交进仓库 fixtures；不重做启动向导或自进化列表。

## 独立验证

```sh
pnpm --filter @harness/web exec vitest run src/pages/evolution/RunDetail.test.ts src/pages/evolution/components/RunDetailConformance.test.ts
pnpm typecheck:web
pnpm test:e2e -- "m10-06"
pnpm lint:web
pnpm verify:flow
```

- 单测覆盖页头空间 badge、工作区折叠区位于 infoPanel 内、策略 / 缓存徽章、可归因 / 非该对象、分布标题与图例、七步详情 / 执行日志页签、准备中文案。
- E2E 在 1408 宽下断言空间 badge 可见、目标与输入 → 流程进度 → 步骤产出的 DOM 顺序、`workspace-panel` 不存在、工作区信息位于 infoPanel、执行日志页签可进入。
- `pnpm typecheck:web` 与 `pnpm lint:web` 通过；`pnpm verify:flow` 通过。

## 验收标准

- 1408 / 1440 宽下同一 run 详情的顺序为：页头（标题 + 状态 + 空间 badge）、目标与输入、流程进度、当前步骤产出；「工作区」不再作为独立卡。
- 目标与输入可见「工作空间」「可归因 / 非该对象」、策略 / 缓存徽标与「本次新增」；「模型（多选）」不再出现；分支名仍可复制。
- 分布标题为「潜在 bad case 的归因结论分布（N 条）」，图例含非该对象、复用缓存与本次新增。
- 七步详情 / 执行日志页签与准备中态在生产与 V2 原型中都可见。
- Before / After 截图（同场景、同视口）附在 PR 描述，Before 明确标注基线版本。

## 门禁与 CI

- 单测与覆盖率：`pnpm test:web`。
- 类型与 lint：`pnpm typecheck:web`、`pnpm lint:web`。
- E2E：`pnpm test:e2e -- "m10-06"`。
- 文档与流程：`pnpm lint:docs`、`pnpm verify:flow`；必要时 `pnpm verify:docs`。
- PR 标题与提交带 `(#<flow issue 编号>)`；CI 全绿后交付人工检视。

## 非目标

- 不新增或修改 API 字段，不新增 Session 总数接口。
- 不改执行日志的数据源、分页、SSE 与错误展示。
- 不改自进化列表、启动向导、对象配置与归因步骤内容。
- 不把生产截图或私有内容写入仓库。
