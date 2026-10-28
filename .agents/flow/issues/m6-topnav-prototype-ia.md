# 顶部导览回归原型：两入口与 Session 激活态

[English](m6-topnav-prototype-ia.en.md) | 中文

```yaml flow
kind: issue
id: m6-06
milestone: m6
depends: []
priority: P1
status: done
scope:
  - apps/web/**
  - tests/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 147
  url: https://github.com/Shadow-Azure/harness-evolution/issues/147
```

## 背景

交互原型的顶部导览只有两个入口（Session 错误查看、自进化），错误详情是 Session 视图内部的子页，由页面内按钮进入；[合并报告](../../../plans/14-15-ui-prototype/merge-completion-report.md)还记录了内部子页签栏整体隐藏、全站只保留单层导览的调整。当前实现却是三个顶层入口：m1-09 脚手架期引入 Sessions/Errors/Evolution 三入口和 `/errors` 占位路由（当时单测即声明 "top-level errors entry arrives later"），m2-09 对齐原型时只对齐了视觉系统，把"Sessions/Errors/Evolution 下划线式导航"写进验收固化至今。后果：顶层 Errors 入口落在一个死胡同——`/errors` 只渲染"请选择会话"空态，既没有跨会话错误列表 API 支撑，也没有返回 Sessions 的动作；同时 `/sessions/:sid` 与 `/sessions/:sid/errors` 上三个导航项全部不高亮（vue-router 的 `router-link-active` 只认 matched 路由记录，平铺兄弟路由不做前缀匹配），与原型"Session 页签在子页保持激活"不符。

## 目标

- 顶栏回归原型信息架构：两个入口（Session 错误查看、自进化），中文标签带副标题，右侧恢复 ID 串联说明。
- 错误详情唯一入口回到 Session 视图内部：`/errors` 退役为重定向到 `/sessions`。
- Session 入口在 `/sessions`、`/sessions/:sid`、`/sessions/:sid/errors` 上保持激活下划线；自进化入口在 `/evolution/**` 保持激活（紫色）。

## 设计依据

- [02-features.md](../../../plans/fullstack-design/02-features.md)：F1"顶部导览：两大视图切换"、F2"ID 体系：深链到 session 错误详情并指定 tab"——顶层只有两个视图，错误详情深链挂在 Session 下。
- [03-frontend-architecture.md](../../../plans/fullstack-design/03-frontend-architecture.md)：路由表只登记 `/sessions/:sid/errors`，不存在顶层 `/errors`。
- [原型](../../../plans/14-15-ui-prototype/harness-evolution.html)与[合并报告](../../../plans/14-15-ui-prototype/merge-completion-report.md)：两入口导览、副标题、右侧串联说明与子页签隐藏的最终形态。

## 实现内容

- `TopNav.vue`：移除 Errors 入口；两入口改为原型中文标签并带副标题（Session 错误查看/会话轨迹与归因、自进化/报告驱动的迭代优化）；激活态改为按路径前缀计算（`/sessions*` → 蓝、`/evolution*` → 紫），不再依赖 `router-link-active`；顶栏右侧新增 ID 串联说明；<1100px 隐藏副标题与说明（原型同规则）。
- `router/index.ts`：`/errors` 由懒加载 ErrorsPage 改为 `redirect: "/sessions"`。
- `errors/Index.vue`：删除 `!rawSessionId` 死分支及其样式（唯一消费方 `/errors` 已退役），错误工作区成为页面唯一形态。
- 同步更新受影响单测（TopNav、App、ui-prototype、router、shell-pages）与 m1-shell E2E。

## 实施步骤

1. 更新 ui-prototype.test 与 TopNav.test 的失败断言（两入口、激活态、副标题）。
2. 改 `TopNav.vue` 与 `router/index.ts`，删除 `errors/Index.vue` 死分支。
3. 同步 App.test、router.test、shell-pages.test 与 m1-shell E2E 断言。
4. 跑全量前端门禁与文档门禁。

## 依赖与交付边界

- 依赖：无（m2 视觉系统已落地）。
- 非目标：不实现跨会话错误列表页与新 API；不改动 Session/Evolution 页面内部导航与深链格式。

## 独立验证

```sh
pnpm test:web -- TopNav ui-prototype App router shell-pages
```

- 全绿：导航恰两个入口、`/errors` 重定向、Session 入口在 `/sessions/:sid/errors` 保持激活。

```sh
pnpm verify:flow; pnpm lint:docs; pnpm verify:web-style; pnpm typecheck:web; pnpm lint:web
```

- 全绿。

```sh
pnpm test:e2e --pattern m1-shell
```

- 1408 与 390 视口下导航为两入口、无横向溢出、无 console 错误；直接访问 `/errors` 落在 `/sessions`。

## 验收标准

- 顶栏恰有两个导航项，文案与原型一致（含副标题）；Session 激活下划线为蓝、自进化为紫。
- `/sessions`、`/sessions/:sid`、`/sessions/:sid/errors` 上 Session 入口保持激活；`/evolution/**` 上自进化入口保持激活。
- 访问 `/errors` 重定向到 `/sessions`，"请选择会话"占位页与 ErrorsPage 无参形态（含相关死代码）移除。
- 390px 视口无横向溢出，副标题与说明隐藏，导航与用户入口可用。
- 现有单测、E2E、typecheck、lint、verify:flow、verify:web-style 全绿。

## 门禁与 CI

- `pnpm verify:flow`：新 issue 三件套与状态机。
- `pnpm lint:docs`：新增 Agent Note 双语配对。
- `pnpm verify:web-style`：顶栏新增样式颜色须取自设计 token。
- `pnpm verify:bundle`：移除 `/errors` 懒加载入口后首屏闭包不得回退。
- `pnpm test:gates`：未改门禁脚本，保持绿。

## 非目标

- 不做全局错误列表：跨会话 bad-case 查询属新后端能力，若需要另立 issue。
- 不改错误详情工作区的信息结构与交互（左栏/执行流/双 Tab 不动）。
- 不改品牌副标题（"轨迹诊断与自进化"是产品标语，原型的"融合原型"是制作期标签，无产品语义）。
- 不处理 `flow-new-issue.mjs` CLI 的 Windows 入口缺陷（m6-05 已记录，另立 issue）。
