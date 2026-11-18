# 无轨迹 bad case 详情保留错误详情壳层

[English](m12-bad-case-trace-shell.en.md) | 中文

```yaml flow
kind: issue
id: m12-15
milestone: m12
depends:
  - m12-07
priority: P1
status: ready
scope:
  - apps/web/src/pages/errors/**
  - tests/e2e/m12-07-trace-state.test.mjs
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
adr: []
github:
  number: 357
  url: https://github.com/Shadow-Azure/harness-evolution/issues/357
```

## 背景

m12-07 把「bad case 行存在但 Session 尚未落库」从 `404 BAD_CASE_NOT_FOUND` 改成 `409/503` 加 `TraceStatusPanel`，总览列表与接口语义已经对齐。但错误详情页把状态分支实现成整页替换：`trace-mode` 只渲染一张居中的状态面板，`ErrorSidebar` 和 `error-head` 都留在 `v-else` 分支里，于是用户看不到当前 case、对象、上报时间、归因状态，也失去「返回 Session」等壳层动作。V2 原型只替换 `<main>` 内的执行流与详情 tab，侧栏和头部始终保留；生产与原型在 1440px 下的信息架构因此不一致（issue #357）。

## 目标

- `trace-mode` 保留 340px 侧栏与 `error-head`，只把执行流、问题描述/归因 tab 换成 `TraceStatusPanel`。
- 无 Session 时侧栏展示当前 case 作用域内容：标题、`syncStatus` 徽标、bad case ID、对象名，以及归因空态或计数；不伪造会话内其它 case。
- `error-head` 展示根会话 ID、上报时间（`details.createdAt`）、对象名、`1 个 bad case` 与归因计数。
- `返回 Session` 只在 Session 可读时可用；无 Session 时渲染禁用态，不产生新的 404 死链。
- 保持 409/503/404 错误码、`details` 字段与列表状态不变；已就绪详情不回归。

## 设计依据

- [08 §7 错误详情页](../../../plans/fullstack-design/08-frontend-implementation.md#7-错误详情页pageserrorsindexvue)：340px 侧栏 + `error-head` + 执行流 + 双 tab 的布局与数据来源。
- [05 §3.8.1 bad case 轨迹状态](../../../plans/fullstack-design/05-api-design.md#381-bad-case-轨迹状态)：409/503 与 `details` 字段、404 语义。
- [V2 原型错误详情](../../../plans/ui-prototype-v2/harness-evolution.html)：`traceUnavailable` 只替换 `<main className="err-main">` 内的执行流与详情 tab。
- [2026-11-17 bad case 无 Session 时表达轨迹状态](../../notes/implemented/bug-fix/2026-11-17-bad-case-session-trace-status.md)：轨迹状态派生与详情错误码。

## 实现内容

- 调整 `pages/errors/Index.vue`：把 `ErrorSidebar` 与 `error-head` 提到状态分支之外；`traceStatus` 存在时在 `<main>` 内渲染状态面板，不再收窄为单栏。
- 扩展 `ErrorSidebar`：新增 `trace` 与归因状态入参；无 Session 时展示当前 case 的标题、ID、对象名、`syncStatus` 徽标与归因空态/计数；`返回 Session` 在无 Session 时禁用。
- `error-head` 在 trace 分支使用 `details.createdAt`、`details.objectName`、路由 `sid` 与归因接口 `total`，并同样禁用无 Session 的返回入口。
- 更新组件测试，覆盖 pending/unavailable 两种状态下侧栏、头部、状态面板同时存在，flow/tab 不渲染，以及归因计数。
- 扩展 `tests/e2e/m12-07-trace-state.test.mjs`，在 1440×960 下断言壳层与禁用返回入口。
- 不新增 case 读端点：验收所需字段已由 503 `details`、路由 `sid` 与 `GET …/bad-cases/{id}/attributions` 提供。

## 实施步骤

1. 重构 `Index.vue` 模板与 `trace-mode` 样式，保留两栏布局和头部。
2. 给 `ErrorSidebar` 增加 case 作用域分支与归因状态展示。
3. 更新 `Index.test.ts`、`TraceStatusPanel` 相关测试与 `m12-07` E2E 断言。
4. 运行 Web 单测、类型检查、lint 与 `m12-07` E2E；生成 1440px 对照截图。
5. 更新 Agent Note 与 PR 证据，等待 CI 与检视。

## 依赖与交付边界

- 依赖：m12-07 的轨迹状态派生与 `BAD_CASE_SESSION_PENDING` / `BAD_CASE_SESSION_UNAVAILABLE` 错误码。
- 交付边界：只改 Web 错误详情页与其测试、流程/笔记与检视文档；不改后端读取模型、错误码、调度策略或总览。
- 无 Session 时不展示同根其它 case；兄弟 case 列表需要新的 case 级读模型，本 issue 不引入。

## 独立验证

```sh
cd apps/web && pnpm exec vitest run src/pages/errors/Index.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- --pattern m12-07-trace-state
```

- 组件测试：pending/unavailable 下存在 `.error-sidebar`、`.error-head`、`[data-testid=trace-status-panel]`，`role=tab` 与 `.sidebar-filter` 为 0；执行流不渲染。
- E2E：从总览进入未就绪 case 后，侧栏含 case 标题与根会话 ID，头部含 `1 个 bad case` 与对象名，返回 Session 为禁用态。
- 截图：1440×913 浅色主题下，未就绪详情与原型一致为两栏壳层 + 状态面板；与 issue #357 的 `proto-after-detail.png` 并排对比。

## 验收标准

- 未就绪 case 的 `查看` 页同时具备错误详情左栏、错误详情头部与轨迹状态面板；执行流、问题描述、归因 tab 不渲染。
- `error-head` 展示根会话 ID、上报时间、对象名、`1 个 bad case` 与归因计数；页面不再只有一张居中面板。
- `返回 Session` 只在 Session 可读时可用；无 Session 时没有新增 404 死链。
- 已就绪 case 详情保持侧栏、执行流、双 tab 与原有返回入口。
- Session 维度接口仍返回 409/503 与原有 `details`；真正不存在的 case 仍 404；列表状态字段不变。

## 门禁与 CI

- `pnpm lint:web`、`pnpm typecheck:web`、`pnpm test:web`。
- `pnpm test:e2e -- --pattern m12-07-trace-state`（CI e2e lane）。
- `node scripts/verify-flow.mjs --diff origin/main` 与 `pnpm test:gates`。
- `pnpm verify:docs`（Agent Note 与流程文件双语配对）。

## 非目标

- 不修改轨迹状态映射、409/503/404 错误码与调度重试策略。
- 不新增 case 详情读端点，不扩展 503 `details` 契约。
- 不重做总览或错误详情视觉，不恢复已裁撤的时间线页。
- 不处理 #348 的登录态/HTTPS 问题。
