# 工作空间总览页面与错误详情下钻

[English](m8-04-workspace-overview-ui.en.md) | 中文

```yaml flow
kind: issue
id: m8-04
milestone: m8
depends:
  - m7-08
  - m8-03
priority: P1
status: in-progress
scope:
  - apps/web/src/pages/overview/**
  - apps/web/src/api/**
  - apps/web/src/components/layout/**
  - apps/web/src/router/**
  - apps/web/src/router.test.ts
  - apps/web/src/ui-prototype.test.ts
  - apps/web/src/composables/**
  - apps/api/app/config.py
  - apps/api/app/main.py
  - packages/contracts/src/**
  - tests/e2e/**
  - scripts/**
  - .github/**
  - plans/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 234
  url: https://github.com/Shadow-Azure/harness-evolution/issues/234
```

## 背景

空间用户需要在一个页面看到来源、趋势和可筛选 bad case 列表，并从列表回到对应错误详情。

## 目标

- 实现 statstrip、来源多选、堆叠趋势和列表。
- URL 保存全部筛选条件。
- 点击 bad case ID 深链到问题描述 Tab。

## 设计依据

- [08 §6](../../../plans/fullstack-design/08-frontend-implementation.md)：总览页面结构。
- [design-v2.md §5](../../../plans/ui-prototype-v2/design-v2.md)：总览原型。

## 实现内容

- 图表使用自研 SVG 和现有 token。
- 时间窗口 >92 天时展示服务端降级粒度。
- 空态区分无数据和筛选无命中。
- URL 是筛选的唯一事实源：`tab=cases`、`range=7|30|90|custom`、`from`/`to`（仅自定义窗口）、`grain=day|week|month`、`objects`（逗号分隔，空 = 全部，多选取并集，chip 逐项移除）、`page`、`type`（自身 / 发现前置步骤统计格下钻）。默认 `range=90`、`grain=week`；非法或缺失值回落默认；切换空间重置筛选。
- 统计条、趋势与来源分布、bad case 列表各自请求与三态；区块级重试，不整页 spinner。点击时间桶把列表窗口切到该桶的起止日期；bad case ID 新窗口打开 `/workspaces/:wid/sessions/:sid/errors?case=<id>&tab=desc`。
- 总览成为空间默认落地页（`/workspaces/:wid` 重定向 `/overview`，登录与空间选择的默认目标同源）；顶栏新增「总览」且位于 Sessions 之前；Session 深链保持原路径。
- `tab=targets` 重定向回 `tab=cases` 并提示：进化对象总览（F25）延后到 M11，页面保留禁用入口而不是死控件。
- 已知缺口：m8-03 不提供「对象 × 时间桶」计数，本 issue 不伪造 SourceMatrix，来源分布以 top 6 + 其余折叠呈现；该矩阵需后续 API 字段，不在前端拼页面数据。
- 契约类型由 m8-03 生成物经 `packages/contracts/src/overview.ts` 再导出，未新增或修改 HTTP 接口。

## 实施步骤

1. 先写筛选恢复与下钻测试。
2. 实现统计条、图表、来源和分页列表。
3. 补加载、空、错误三态 E2E。

## 依赖与交付边界

- 依赖：m7-08、m8-03
- 交付边界：F25 进化对象总览延后到 M11。
- 交付边界：SourceMatrix（对象 × 时间桶明细）随 m8-03 的聚合口径一起顺延，本 issue 不实现。

## 独立验证

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern "m8-04 overview"; pnpm test:e2e -- --pattern "m1-shell|m7-08 workspace-shell"
```

- 刷新后筛选不变，URL 与请求参数一致。
- 空 objects 表示全部，并集与 chip 移除正确。
- 下钻 URL 选中正确 case 的问题描述 Tab。
- 390px 无横向溢出，控制台无报错。

## 验收标准

- 页面与原型信息架构一致。
- 图表与列表互不阻塞。

## 门禁与 CI

- Web、E2E、bundle 与 flow 门禁。

## 非目标

- 不引入第三方图表库。
- 不做跨空间汇总。
