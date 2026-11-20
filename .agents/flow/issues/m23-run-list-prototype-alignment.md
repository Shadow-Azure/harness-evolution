# 自进化历史记录卡补全工作空间 / 潜在策略 / 缓存标签

[English](m23-run-list-prototype-alignment.en.md) | 中文

```yaml flow
kind: issue
id: m23-01
milestone: m23
depends:
  - m5-04
  - m10-06
priority: P2
status: done
scope:
  - apps/api/app/service/evolution/**
  - apps/api/tests/**
  - packages/contracts/**
  - apps/web/src/pages/evolution/**
  - tests/e2e/**
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-20-run-list-prototype-alignment.md
github:
  number: 418
  url: https://github.com/Shadow-Azure/harness-evolution/issues/418
```

## 背景

生产「自进化 → 历史记录」的运行卡片只有对象版本、时间窗与模型 chip，缺少 V2 原型第二行的「工作空间」「潜在策略」「缓存」三枚标签；卡片右上把创建人拼在时间前，与原型只显示时间不一致。运行配置其实已经写入 `evolution_runs`（`potential_policy`、`cache_enabled`、`workspace_id`），缺的是 `EvolutionRunService._card()` 的投影与 `EvolutionRunCard` 契约字段。设计文档 05 §3.5 的 `RunCard` 示例早已包含 `policy` 与 `cacheEnabled`，实现与设计之间是投影缺口而不是新的产品需求。完整对照与截图见 [GitHub #414](https://github.com/Shadow-Azure/harness-evolution/issues/414)。

## 目标

- 历史卡片在对象版本与时间窗之后显示工作空间、`默认潜在策略` / `自定义潜在策略`、`复用缓存` / `不复用缓存` 三枚标签，顺序与 V2 原型一致。
- `EvolutionRunCard` 契约增加只含展示所需 preset 的 `policy` 与 `cacheEnabled`；工作空间名由页面上下文（当前路由工作空间）渲染，列表始终按工作空间过滤，不在卡片 DTO 重复空间信息。
- 卡片右上只显示时间，创建人不再在列表渲染；`createdBy` 保留在 DTO 供详情与审计，设计文档 05 / 08 与原型口径同步。
- 旧 run 没有 `potential_policy` / `cache_enabled` 时按默认策略与不复用缓存展示，不报错、不伪造自定义策略。
- 六项统计、状态徽标、completed 终评行、failed 无终评行、整卡点击与 error tooltip 不回归。

## 设计依据

- [05 §3.5 自进化运行](../../../plans/fullstack-design/05-api-design.md#35-自进化运行)：`RunCard` 的 `policy`、`cacheEnabled`、`createdBy` 字段与列表口径。
- [08 §8 自进化列表页](../../../plans/fullstack-design/08-frontend-implementation.md#8-自进化列表页pagesevolutionindexvue)：历史卡的组件树、badge、终评行与空态。
- [V2 原型运行列表](../../../plans/ui-prototype-v2/harness-evolution.html)：`evRunCard()` 第二行的对象版本、时间窗、工作空间、策略、缓存顺序，以及右上只显示时间。
- [06 自进化表](../../../plans/fullstack-design/06-database-design.md)：`evolution_runs.potential_policy`、`cache_enabled`、`workspace_id` 的存储事实。
- [Agent Note](../../notes/implemented/bug-fix/2026-11-20-run-list-prototype-alignment.md)：投影字段、空间来源与创建人取舍。

## 实现内容

- `apps/api/app/service/evolution/runs.py`：新增 `EvolutionRunPolicy`（`preset: default | custom`），`_card()` 从 `run.potential_policy` 投影 `policy`（缺失或未知 preset 归一为 `default`）与 `cache_enabled`；`EvolutionRunDetail` 继承卡片字段，详情自动获得同一快照。
- `packages/contracts`：运行 `pnpm contract:generate` 更新 `openapi.json` 与生成类型，不手改。
- `apps/web/src/pages/evolution/components/RunCard.vue`：`run-meta` 在时间窗后渲染工作空间 chip、策略 chip、缓存 chip；时间只显示 `createdAt`，移除创建人前缀；保留模型 chip 与既有统计、终评行与 tooltip。
- `apps/web/src/pages/evolution/Index.vue` / `components/RunGroup.vue`：从 auth store 读取当前工作空间名并下传给卡片；缺失时按空串处理，不伪造空间名。
- `apps/web/src/pages/evolution/components/RunCard.test.ts`、`Index.test.ts`、`RunGroup.test.ts` 与其它卡片 fixture：覆盖 default / custom、cache true / false、旧 run 无策略、创建人不再渲染、工作空间名来源。
- `apps/api/tests/m5-04-run-list/**`：服务测试断言 `policy`、`cacheEnabled` 投影与旧数据默认值。
- `plans/ui-prototype-v2/harness-evolution.html`：保持三枚标签与只显示时间；补一个 failed 运行样例与红色失败徽标，避免后续把「失败无终评行」误判为样式缺失。
- `plans/fullstack-design/05-api-design.md` 与 `08-frontend-implementation.md`：同步 `policy` / `cacheEnabled` 已经是卡片字段、空间名来自页面上下文、创建人只在 DTO 的口径；新增 Agent Note 记录取舍。

## 实施步骤

1. 在服务层投影 `policy` 与 `cache_enabled`，补 default / custom / 旧数据 API 测试。
2. 运行 `pnpm contract:generate` 并提交契约与生成类型。
3. 改造 `RunCard.vue` 的 meta 行与时间显示，页面下传工作空间名，更新组件测试。
4. 更新其它 `EvolutionRunCard` fixture 与 Index / RunGroup 测试。
5. 补齐 V2 原型 failed 样例与设计文档，新增 Agent Note，运行聚焦门禁。
6. 同视口 1500×837 重拍 Before / After，Before 用 main 基线，附 PR 描述。

## 依赖与交付边界

- 依赖：m5-04（运行列表 API 与分组）、m10-06（七步运行详情与卡片契约消费方）。
- 交付边界：只改运行列表卡片、`EvolutionRunCard` 投影与契约、对应测试、原型样例与设计文档 / Agent Note；不改运行详情、向导、归因 / 聚类 / 评测算法、数据库 schema 与列表排序。

## 独立验证

```sh
pnpm contract:check
pnpm typecheck:web
pnpm lint:web
pnpm --filter @harness/web exec vitest run src/pages/evolution/components/RunCard.test.ts src/pages/evolution/Index.test.ts src/pages/evolution/components/RunGroup.test.ts
apps/api/.venv/bin/python -m pytest apps/api/tests/m5-04-run-list -q
pnpm test:e2e -- --pattern evolution
pnpm verify:flow
```

- 预期：契约包含 `policy` 与 `cacheEnabled` 且无破坏；历史卡显示三枚标签与工作空间名；default / custom 与 cache true / false 文案正确；旧 run 显示默认策略；卡片右上只有时间；六项统计与终评行不回归；流程门禁通过。

## 验收标准

- 生产历史记录卡依次出现工作空间、潜在策略、缓存三枚标签，顺序与原型一致，工作空间名与当前路由空间一致。
- `policy.preset` 与 `cacheEnabled` 由后端投影；无策略旧数据展示为默认策略。
- 创建人显示有明确结论：列表只显示时间，`createdBy` 保留在 DTO，原型与设计文档同口径。
- completed 运行仍有 best / 初始 / Δ / 接纳行，failed 运行不伪造终评数据。
- 契约、类型、单测、API 测试和聚焦 E2E 通过；Before / After 截图同视口并附 PR。

## 门禁与 CI

- 契约：`pnpm contract:generate` 后 `pnpm contract:check`。
- 静态：`pnpm typecheck:web`、`pnpm lint:web`。
- 单测：`pnpm --filter @harness/web exec vitest run …`、`pnpm test:api -- -k evolution_run`。
- E2E：`pnpm test:e2e -- --pattern evolution`。
- 文档与流程：`pnpm lint:docs`、`pnpm verify:flow`，必要时 `pnpm verify:docs`。
- PR 标题与提交带 `(#<flow issue 编号>)`；CI 全绿后交付人工检视。

## 非目标

- 不改数据库 schema、归因 / 聚类 / 评测算法、SSE、七步 key 与分页。
- 不改运行详情页、启动向导、对象配置与归因步骤内容。
- 不重做列表页布局或页面宽度，不调整列表排序与六项统计口径。
- 不把生产 Session 内容或截图提交进仓库 fixtures。
