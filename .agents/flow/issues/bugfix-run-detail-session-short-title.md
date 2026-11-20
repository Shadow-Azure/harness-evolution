# 运行详情第 2 步 Session 关联显示短标题并固定列宽

[English](bugfix-run-detail-session-short-title.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-02
milestone: bugfix
depends:
  - m21-01
priority: P2
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - .agents/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 444
  url: https://github.com/Shadow-Azure/harness-evolution/issues/444
```

## 背景

生产「自进化 → 运行详情 → 第 2 步 Session 关联」把 Session 的首条 prompt 全文渲染进表格。SWE-bench 类 Session 的首条用户消息就是整段任务 prompt（本次样本 3337 字符），在 1500×837 CSS 视口下把首行撑到 329px、Session 列撑到 1247px，其余三列被压到 43–79px，关联证据无法核对；V2 原型同位置用短标签加完整 Session ID，四列同屏。产品问题、生产/原型量化对照与证据见 [issue #440](https://github.com/Shadow-Azure/harness-evolution/issues/440)。

根因是数据通路缺字段叠加展示层无约束：Session 关联结果与 `session_families.short_title` 本来就有短标签，但运行准备阶段写入 `stats.sessionRows` 时只持久化 `sessionId/title/objectTriggerAt/badCaseCount`，丢掉了 `short`；`StepSessionRow` 契约也没有该字段。前端 `StepSessions.vue` 直接渲染 `row.title`，表格是自动布局且单元格允许换行，长 prompt 参与列宽计算并逐行换行。启动向导第 2 步（[#404](https://github.com/Shadow-Azure/harness-evolution/issues/404)）已按同一「短标签 + 完整标题悬停 + 固定列宽」方案修复，运行详情这一处尚未覆盖。

## 目标

- 第 2 步 Session 单元格显示可读的短标签，单行截断加省略号，完整标题放进 `title` 悬停提示；Session ID 展示保持不变。
- 表格改固定布局并给四列稳定宽度，1440/1500 宽视口下 `对象触发点`、`bad case`、`潜在 bad case` 不被长标题挤出。
- 步骤接口返回 `short`，来源是 `session_families.short_title`；存量 run 的 `stats.sessionRows` 没有 `short` 时用 `title[:120]` 兜底，不要求重新准备历史 run。
- 关联 Session 数、分页、排序、跳过与版本未知统计不变。

## 设计依据

- [05 §3.6 七步产出](../../../plans/fullstack-design/05-api-design.md#36-七步产出七个独立端点)：`steps/sessions` 的 `rows[]` 字段与 4 条/页口径。
- [08 §10.1 运行详情页结构](../../../plans/fullstack-design/08-frontend-implementation.md#101-结构)：V2 七步中第 2 步的表格列与展示约定。
- [V2 原型](../../../plans/ui-prototype-v2/harness-evolution.html)：第 2 步用 `a.sess.short` 加完整 Session ID 渲染，Session 单元格不渲染完整 prompt。
- [issue #440](https://github.com/Shadow-Azure/harness-evolution/issues/440)：生产复现、量化对照与根因分析。

## 实现内容

- `apps/api/app/service/evolution/stages.py`：`StepSessionRow` 增加可空的 `short`；`_v2_session_rows` 读取持久化的 `short`，缺失时回退 `title[:120]`；legacy 行也给出短标签。
- `apps/api/app/service/evolution/prepare.py`：写入 `sessionRows` 时补 `short: session.short`。
- `packages/contracts`：用 `pnpm contract:generate` 更新 `openapi.json` 与生成类型，不手改。
- `apps/web/src/pages/evolution/components/StepSessions.vue`：标题用 `row.short || row.title || "未命名 Session"`，外层 `title` 属性展示完整 `title`；标题单行省略；表格 `table-layout: fixed` 并用 `colgroup` 固定触发点与计数列宽度。
- 测试：API 断言 `sessionRows` 持久化 `short`、阶段接口返回 `short` 且存量行回退；组件测试用超长标题断言显示短标签、悬停保留全文；E2E 用真实浏览器断言长标题不撑高行、四列同屏。
- 文档：05 §3.6 补 `short` 字段，08 §10.1 补第 2 步展示约定；新增 Agent Note 记录数据通路与展示约束的取舍。

## 实施步骤

1. 扩展 `StepSessionRow` 与准备阶段持久化，补 API 单元测试。
2. 运行 `pnpm contract:generate` 并提交契约变更。
3. 调整 `StepSessions.vue` 的标题渲染与表格布局，补组件测试。
4. 在 m10-06 E2E fixture 中加入超长 prompt 标题，断言行高与列宽。
5. 更新设计文档、Agent Note，运行门禁与真实浏览器冒烟，提交 PR。

## 依赖与交付边界

- 依赖：m21-01
- 交付边界：只修运行详情第 2 步的 Session 标题数据通路、标题渲染与表格横向布局；对象出现列、关联算法、bad case 统计、分页排序与 Session ID 格式保持现状。

## 独立验证

```sh
pnpm contract:check
apps/api/.venv/bin/python -m pytest apps/api/tests/evolution/test_m10_04_stages.py apps/api/tests/evolution/test_m10_04_prepare.py apps/api/tests/test_openapi.py
pnpm test:web -- RunDetail
pnpm test:e2e -- --pattern m10-06
pnpm test:gates && pnpm verify:docs && pnpm verify:flow
```

- `sessionRows` 持久化 `short`，阶段接口返回 `short`；缺 `short` 的存量行回退到标题前 120 字符。
- 超长 prompt 下 Session 单元格保持单行，表格无横向溢出，另外三列表头仍在可视范围内。
- 悬停文本等于完整 `title`，标题显示短标签。

## 验收标准

- 1440/1500 宽视口打开运行详情第 2 步，超长 prompt Session 不撑高行、不挤出关联证据列。
- 短标签、完整标题悬停提示与 Session ID 同时存在。
- 关联 Session 数、分页、排序、跳过与版本未知统计不变。
- 存量 run 不重新准备也能正常渲染。
- 组件测试与 E2E 覆盖超长标题回归。

## 门禁与 CI

- 命中 `pnpm contract:check`、`pnpm lint:web`、`pnpm typecheck:web`、`pnpm test:web`、`pnpm test:api`、`pnpm test:e2e`、`pnpm test:gates`、`pnpm verify:docs`、`pnpm verify:flow`。
- PR 标题与提交标题引用本 issue 的 GitHub 编号，并在 PR 描述引用产品 issue #440。

## 非目标

- 不改 `session_families.short_title` 的生成算法，不提取语义标题。
- 不改关联算法、bad case 统计、分页排序或 Session ID 展示格式。
- 不补齐原型多出的「对象出现」列，列口径差异留给单独设计确认。
- 不把生产 Session 内容或截图提交进仓库。
