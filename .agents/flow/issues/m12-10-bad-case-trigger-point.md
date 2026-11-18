# bad case 总览展示可定位的触发点

[English](m12-10-bad-case-trigger-point.en.md) | 中文

```yaml flow
kind: issue
id: m12-10
milestone: m12
depends:
  - m8-04
  - m12-02
  - m12-07
priority: P1
status: backlog
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 337
  url: https://github.com/Shadow-Azure/harness-evolution/issues/337
```

## 背景

生产 bad case 总览当前把原型中的「触发点」列替换成「触发时间」，值来自 `BadCaseListItem.triggerAt`。接口文档同时明确：`triggerAt` 临时等于 `createdAt`，在 m9-04 坐标落地前不能作为真实触发时间或排序依据。

原型同一列展示 `L0`、`L58`、`L91` 等日志行位置，用户可以直接把 bad case 与执行流中的触发线对应起来。生产则显示日期时间，既丢失定位语义，又容易让用户误以为这是对象的真实触发时间。

底层 `bad_cases` 已可能携带 `trigger_line`；问题在于总览契约和读模型没有把该字段投影到 `BadCaseListItem`，前端因此只能用占位 `triggerAt`。

## 目标

- 为总览 bad case 行暴露可空的 `triggerLine`，并保持现有 `triggerAt` 兼容。
- 前端列名恢复为「触发点」，有行号时显示 `L<n>`，无行号时显示诚实空值，不再把 `createdAt` 伪装为触发时间。
- 同一个 bad case 的总览行与错误详情执行流使用同一触发行号来源。
- 通过契约生成、API、前端与 E2E 证明总览定位点和详情触发点一致。
- 若历史数据无 `trigger_line`，不回填猜测值；允许显示「—」并保留从详情或原始事实推导后续定位的路径。

## 证据截图

| 生产环境 | V2 原型 |
| --- | --- |
| [![生产列表触发时间](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-01b-overview-list.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-01b-overview-list.jpeg) | [![V2 原型列表触发点](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-01b-overview-list.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-01b-overview-list.jpeg) |

两图均为 `2816×1576` 的真实浏览器窗口截图。生产列名为「触发时间」并显示日期；原型列名为「触发点」并显示 `L0`、`L91` 等日志行位置。

## 设计依据

- [05 §3.4 问题与归因状态](../../../plans/fullstack-design/05-api-design.md#34-问题bad_case归因状态与-probe)：bad case 的锚点、元数据与展示字段。
- [05 §3.10 总览与空间 Session](../../../plans/fullstack-design/05-api-design.md#310-总览与空间-session)：`BadCaseListItem` 当前 `triggerAt` 的临时语义。
- [05 §4.18 总览与空间 Session 列表](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2)：总览列表契约。
- [05 §9 与原型字段的映射对照](../../../plans/fullstack-design/05-api-design.md#9-与原型字段的映射对照)：原型字段到 API 的映射约束。
- [V2 设计 §5.1 指标与筛选](../../../plans/ui-prototype-v2/design-v2.md#51-指标与筛选)：列表字段与问题类型的展示约定。

## 实现内容

- 在 `packages/contracts` 的 `BadCaseListItem` 增加 `triggerLine: number | null`；保留 `triggerAt`，生成 OpenAPI 与 TS 类型。
- 在 overview repository/service 中从 `bad_cases.trigger_line` 或等价既有列做稳定投影；不得用 `createdAt` 时间或事件下标猜测行号。
- API 响应示例和文档更新为 `triggerLine` 可空，并明确 `triggerAt` 不再作为总览「触发点」列的值。
- `BadCaseTable` 把列标题改为「触发点」，显示 `L${triggerLine}` 或 `—`；保留可访问的完整数值/空值说明。
- 总览行点击后的深链保持现状；错误详情和高亮线继续使用同一行号，不新增重复字段。
- 测试覆盖有行号、空行号、旧响应兼容、深浅链一致和契约快照。

## 实施步骤

1. 写失败测试，证明当前总览只返回 `triggerAt`，无法区分真实触发位置与 `createdAt`。
2. 在共享契约新增可空 `triggerLine`，运行 `pnpm contract:generate`。
3. 扩展总览 repository/service 投影并用 API 测试覆盖 `trigger_line` 为整数和 NULL 的行。
4. 修改 `BadCaseTable` 列名和渲染逻辑，补组件与 E2E 定位断言。
5. 更新 API 文档中的 `BadCaseListItem` 示例、字段语义和原型映射。
6. 运行 contract、type、API、web、E2E、文档与流程门禁。

## 依赖与交付边界

- 依赖：m8-04 提供总览列表，m12-02 提供真实外部契约，m12-07 提供轨迹状态；均已完成。
- 交付边界：只增加总览读取与展示所需的触发行号；不修改触发点计算算法或执行流布局。
- `triggerAt` 保留兼容，若后续有真实时间事件再单独立项定义；本 issue 不把 `triggerAt` 改造成真实时间。
- 历史 NULL 行不做猜测回填；空值必须可在 UI 和 API 中稳定表达。

## 独立验证

```sh
pnpm contract:generate
pnpm contract:check
pnpm test:api -- tests/m8-04-overview
pnpm test:web -- apps/web/src/pages/overview/components/BadCaseTable.test.ts
pnpm test:e2e -- --pattern m12-10
pnpm typecheck
```

- 有 `trigger_line` 的 case 在总览显示 `L<n>`，错误详情高亮同一行。
- `trigger_line` 为 NULL 的 case 显示 `—`，接口返回 `triggerLine: null`，不伪造 `createdAt`。
- 旧客户端只读 `triggerAt` 时不崩溃；生成契约无漂移。
- 数据库查询无 N+1，分页列表每行只获得自己的触发行号。
- E2E 证明总览列、深链和详情高亮一致。

## 验收标准

- `BadCaseListItem.triggerLine` 在 OpenAPI 与 TS 类型中存在且可为 null。
- 总览列名是「触发点」，有值时显示日志行，无值时显示「—」。
- 任何总览行都不再把 `triggerAt` 当作触发点或排序依据。
- 总览与错误详情对同一 case 使用同一触发行号，历史空值不改写。
- 契约、API、web、E2E、文档和流程门禁全部通过。

## 门禁与 CI

- `pnpm contract:generate`、`pnpm contract:check`、`pnpm test:api`、`pnpm test:web`、`pnpm test:e2e`、`pnpm typecheck`、`pnpm lint:docs`、`pnpm verify:flow`。
- PostgreSQL/MySQL 兼容查询测试与至少一个真实 JSONL fixture 的行号断言。

## 非目标

- 不改变 bad case 触发点的计算、lane DAG 或问题卡布局。
- 不把 `createdAt`、事件数组下标或时间戳猜测为行号。
- 不为历史 NULL 行批量回填虚构值。
- 不在本 issue 增加列表级筛选。
