# 总览趋势近 7 天按周聚合，11-19 当天数量不可见（原型已改为日粒度，待实现）

[English](m14-overview-7d-day-grain.en.md) | 中文

```yaml flow
kind: issue
id: m14-02
milestone: m14
depends: []
priority: P1
status: ready
scope:
  - apps/web/src/pages/overview/**
  - tests/e2e/**
  - plans/ui-prototype-v2/**
  - plans/fullstack-design/**
  - .agents/notes/**
  - .agents/flow/**
adr:
  - ../../notes/implemented/feature/2026-11-19-overview-7d-day-grain.md
github:
  number: 375
  url: https://github.com/Shadow-Azure/harness-evolution/issues/375
```

## 背景

2026-11-19 生产总览页反馈：11-19 上报的 4 条 bad case 在列表里可见，但「bad case 趋势」只有 `11-09`、`11-16` 两个周桶，没有 11-19 的独立时间桶。核对数量：顶部「已上报 33」、列表「共 33 条」、11-16 柱合计 33，说明数据已计入 11-16 周桶，不是入库或统计口径丢数；问题在于近 7 天窗口仍沿用周粒度，且图表只显示桶起始日。

原型已先按产品预期修改：`plans/ui-prototype-v2/harness-evolution.html` 选择近 7 天时默认切日粒度；生产实现尚未跟进。修改前/后截图与完整取证见 GitHub #375。

## 目标

- 近 7 天快捷范围默认日粒度，趋势返回 7 个日桶，当天数据可见。
- 近 30/90 天快捷范围默认周粒度；用户之后手动选择日/周/月不被数据刷新覆盖。
- `?range=7` 未显式给合法 `grain` 时规范化为 `day`；显式 `?range=7&grain=week` 继续尊重用户选择。
- 原型、设计文档和生产实现使用同一默认规则；不新增 API、数据库或统计口径。

## 设计依据

- [08 §6.2 交互与 URL](../../../plans/fullstack-design/08-frontend-implementation.md#62-交互与-url)：总览时间/粒度、URL 状态与列表独立性。
- [05 §4.18 总览读端点](../../../plans/fullstack-design/05-api-design.md#418-总览读端点)：trend 的 `grain` 与窗口语义，服务端已支持 day/week/month。
- [V2 设计 §5.1 指标与筛选](../../../plans/ui-prototype-v2/design-v2.md#51-指标与筛选)：时间/粒度控件与总览交互。
- [V2 原型总览](../../../plans/ui-prototype-v2/harness-evolution.html)：本轮已改为近 7 天默认日粒度。
- Agent Note：[2026-11-19-overview-7d-day-grain](../../notes/implemented/feature/2026-11-19-overview-7d-day-grain.md)。

## 实现内容

- `apps/web/src/pages/overview/overviewUrl.ts`：`parseOverviewQuery` 在 `range=7` 且没有显式合法 `grain` 时落到 `day`；显式 grain 优先。
- `apps/web/src/pages/overview/Index.vue`：`setRange` 在快捷范围变化时联动粒度——7 天 → day，30/90 天 → week；自定义区间保持当前粒度。
- `apps/web/src/pages/overview/overviewUrl.test.ts`、`Index.test.ts`：覆盖 7 天默认 day、显式 week 保留、30/90 默认 week、手动粒度在范围变化前不被覆盖。
- `tests/e2e/m8-04-overview.test.mjs`：覆盖点击近 7 天后 URL `grain=day`、7 个日桶、当天桶可见，以及 30/90 回到周粒度。
- `plans/fullstack-design/08-frontend-implementation.md`：补充时间范围与粒度联动约定。
- 不改 `apps/api`、`packages/contracts`、数据库迁移或统计查询。

## 实施步骤

1. 修改 URL 解析与页面 `setRange` 的默认粒度联动。
2. 补单元/组件测试，覆盖默认、显式覆盖和快捷范围切换。
3. 补 E2E：近 7 天 7 个日桶、当天桶可见、30/90 周粒度。
4. 更新设计文档与 Agent Note，运行 typecheck/lint/单测/聚焦 E2E。
5. 提交 PR；PR 描述附修改前/后截图与冒烟证据，CI 通过后按 review 流程处理。

## 依赖与交付边界

- 依赖：无新依赖；后端 trend 已支持 day grain，本 issue 只改前端默认与 URL 规范化。
- 交付边界：只改总览时间/粒度联动、对应测试和设计文档；不改图表几何、列表筛选、接口字段、数据结构或权限。
- 近 7 天显式 `grain=week` 的旧链接必须保持周视图；近 30/90 天默认周粒度不回归。

## 独立验证

```sh
pnpm test:web -- --run src/pages/overview/overviewUrl.test.ts src/pages/overview/Index.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- --pattern m8-04-overview
pnpm verify:flow --diff origin/main
```

- 预期：单测覆盖 7 天默认 day 与显式 grain；E2E 中近 7 天趋势有 7 个 `[data-bucket]`、当天桶存在且 hint 为「按日聚合」；30/90 天 hint 为「按周聚合」；typecheck/lint/CI 通过。

## 验收标准

- 点击「近 7 天」后 URL 为 `range=7&grain=day`，图表出现 7 个日桶，11-19/当天桶可见且计数正确。
- 直接打开 `?range=7` 规范化为 day；显式 `?range=7&grain=week` 仍显示周桶。
- 点击「近 30 天」「近 90 天」默认周粒度；手动切到月后，下一次时间范围变化前不被覆盖。
- 近 30/90 天现有 14 个周桶的展示、列表筛选和统计不回归。
- 原型与实现默认一致，PR 内含修改前/后截图。

## 门禁与 CI

- `verify:flow --diff origin/main` 覆盖本 issue 引用与 scope。
- `web-static`（lint/typecheck/样式）、`unit-tests`、`e2e`、`docs-flow` 通过。
- PR 标题含 `(#375)`，PR 描述附原型修改前/后截图与冒烟结果。

## 非目标

- 不新增“今日新增”指标、不重做趋势图、不改图表几何或配色。
- 不改 bad case 入库、同步、时区、统计口径或 API 契约。
- 不改变显式 `grain` 的语义，也不把长窗口默认改为日粒度。
