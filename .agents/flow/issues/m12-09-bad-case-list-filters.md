# 补齐 bad case 列表级筛选

[English](m12-09-bad-case-list-filters.en.md) | 中文

```yaml flow
kind: issue
id: m12-09
milestone: m12
depends:
  - m8-04
  - m12-07
priority: P1
status: done
scope:
  - apps/web/src/pages/overview/**
  - apps/web/src/api/**
  - apps/api/app/api/overview.py
  - apps/api/app/service/overview/**
  - apps/api/app/db/crud/overview.py
  - apps/api/tests/m8-03-workspace-overview/**
  - apps/api/tests/test_openapi.py
  - packages/contracts/**
  - tests/e2e/m8-04-overview.test.mjs
  - tests/e2e/m12-08-overview-actions-context.test.mjs
  - tests/e2e/m12-09-bad-case-list-filters.test.mjs
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 336
  url: https://github.com/Shadow-Azure/harness-evolution/issues/336
```

## 背景

生产环境与 V2 原型的 bad case 列表对照显示，原型在列表头直接提供开始日期、结束日期、上报来源和问题类型四个筛选控件，生产列表只有标题、总数和分页。

生产页面上方的全局时间范围、粒度和来源筛选服务于趋势图，无法代替原型定义的列表级独立筛选。用户当前不能在保留全局图表上下文的同时，单独缩小某个列表查询。

该差异与是否有生产数据无关。截图时生产已有 9 条 bad case，仍没有列表级筛选项；原型在 26 条数据下可按列表字段独立过滤。

## 目标

- 在 bad case 列表头提供开始日期、结束日期、上报来源和问题类型筛选。
- 列表筛选与趋势图的全局时间/来源筛选保持独立，默认空值不限制结果。
- 任一筛选变化把页码重置到 1，并展示可解除的筛选状态和真实空态。
- 把列表筛选写入 URL，刷新、返回和分享后保持。
- 复用现有 overview bad-case 查询端点；只有现有契约不足时才做最小字段扩展。

## 证据截图

| 生产环境 | V2 原型 |
| --- | --- |
| [![生产 bad case 列表](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-01b-overview-list.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-01b-overview-list.jpeg) | [![V2 原型 bad case 列表](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-01b-overview-list.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-01b-overview-list.jpeg) |

两图均为 `2816×1576` 的真实浏览器窗口截图。原型在列表头提供日期、来源和类型筛选；生产仅显示标题、总数和分页。

## 设计依据

- [08 §6.1 总览结构](../../../plans/fullstack-design/08-frontend-implementation.md#61-结构)：总览统计、图表和列表的模块边界。
- [08 §6.2 交互与 URL](../../../plans/fullstack-design/08-frontend-implementation.md#62-交互与-url)：筛选状态与 URL 的持久化。
- [05 §4.18 总览与空间 Session 列表](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2)：bad case 列表查询与分页参数。
- [05 §7 分页、排序与过滤约定](../../../plans/fullstack-design/05-api-design.md#7-分页排序与过滤约定)：空筛选、并集和分页约定。
- [V2 设计 §5.1 指标与筛选](../../../plans/ui-prototype-v2/design-v2.md#51-指标与筛选)：列表筛选独立于图表。

## 实现内容

- 在 `BadCaseTable` 列表头增加日期区间、来源和类型控件；来源选项复用 overview 的 object/source 列表，不新增第二套枚举。
- 在 `overviewUrl.ts` 增加列表专用查询状态，例如 `listFrom`、`listTo`、`listObject`、`listType`、`listPage`；命名以最终实现和既有 URL 兼容规则为准。
- 列表查询使用独立的 `queryKey` 和数据请求，不因趋势筛选变化而隐式重置；全局筛选仍决定图表和统计。
- 列表日期为空时必须真正不限时间：现有列表端点默认只取 90 天，因此增加可选 `allTime=true`（服务端跳过日期条件），这是本 issue 唯一的最小契约扩展；不新增端点或表。
- 日期区间非法时不发请求，保留上一个有效结果并在控件附近显示可操作错误；清空后恢复无限制。
- 空结果表明当前筛选无命中，并提供清除筛选；未筛选且总数为 0 时仍使用空间级空态。
- 筛选变化重置 `listPage=1`；分页只修改 `listPage`。浏览器后退/前进恢复全部列表筛选。
- 单元测试覆盖筛选变更、URL 往返、分页重置、非法日期和空态；E2E 覆盖筛选后刷新与返回。

## 实施步骤

1. 先为列表 URL 状态、分页重置和空态写失败测试。
2. 扩展 overview URL 解析/序列化，保持旧 URL 可解析。
3. 把列表查询状态与趋势全局筛选拆开，复用现有 overview API 参数。
4. 在 `BadCaseTable` 增加四组控件与清除入口，补键盘和 aria 标签。
5. 补 SQLite/HTTP 与 E2E 的筛选命中、无命中和刷新恢复场景。
6. 更新前端设计现状与 Agent Note，运行类型、web、E2E 和文档门禁。

## 依赖与交付边界

- 依赖：m8-04 提供总览列表，m12-07 提供轨迹状态；两者均已完成。
- 交付边界：只补列表筛选和 URL 状态；不改趋势图统计语义、不新增全局筛选。
- 「触发点」列及对应 API 字段由 m12-10 独立处理；本 issue 不把两者的测试和迁移混在一起。
- 不引入客户端全量过滤；分页和筛选必须由服务端查询承担。

## 独立验证

```sh
pnpm test:web -- apps/web/src/pages/overview
pnpm test:api -- tests/m8-03-workspace-overview
pnpm test:e2e -- --pattern m12-09
pnpm typecheck:web
pnpm verify:flow
```

- 四个列表筛选可单独或组合使用，并返回与 API 查询一致的结果。
- 任一筛选变化回到第 1 页；分页不丢失筛选。
- 刷新、浏览器返回和复制 URL 后筛选条件不变。
- 非法日期、无命中和空间无数据呈现三个不同状态。
- 趋势与统计不受列表筛选影响。

## 验收标准

- bad case 列表头具备开始/结束日期、上报来源和问题类型控件。
- 列表筛选与页面全局筛选独立，空值表示不限制。
- 筛选及分页状态可通过 URL 恢复，旧 URL 兼容。
- 服务端分页结果与总数一致，不出现客户端全量过滤。
- 空态和错误态可恢复，键盘与屏幕阅读器可操作。
- 新测试和文档通过 CI，既有总览、轨迹状态与下钻不回归。

## 门禁与 CI

- `pnpm test:web`、`pnpm test:api`、`pnpm test:e2e`、`pnpm typecheck:web`、`pnpm verify:flow`、`pnpm lint:docs`。
- CI 必须包含筛选 + 分页组合、旧 URL 兼容和空结果分支。

## 非目标

- 不改变趋势图和统计卡的计算口径。
- 不增加客户端全量数据过滤或新表。
- 不在本 issue 改变「触发时间」为「触发点」；该字段语义由 m12-10 负责。
- 不重做列表视觉系统或分页组件。
