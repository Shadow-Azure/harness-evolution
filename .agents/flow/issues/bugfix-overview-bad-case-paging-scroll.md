# 总览 bad case 列表首次翻页出现刷新感并跳到顶部

[English](bugfix-overview-bad-case-paging-scroll.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-76
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - apps/web/src/pages/overview/**
  - apps/web/src/composables/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-28-overview-bad-case-paging-scroll.md
github:
  number: 670
  url: https://github.com/Shadow-Azure/harness-evolution/issues/670
```

## 背景

用户反馈：总览页 bad case 列表点击「下一页」，首次进入未翻过的页时出现页面刷新感并跳到页面顶部；返回后再次进入已翻过的页则不会跳顶。问题只在未缓存页首次出现，说明它与分页请求的加载态有关，而不是路由或整页重载。

当前 `BadCaseTable.vue` 在 `loading` 时用 4 行骨架替换整张表和分页条；`useOverviewCases` 又按 `page` 分页，未访问页没有缓存，进入时必然经历这段加载态。列表内容与分页条同时消失会让总览滚动容器内容高度骤降，浏览器把 `scrollTop` 夹到新的最大值，表现为跳回页面顶部。已访问页有缓存，数据同步就绪，不出现这段收缩，因此不复现。

## 目标

- 首次访问和再次访问分页均保持列表阅读位置，不触发整页刷新或滚动跳顶。
- 加载期间保留上一有效列表结果与分页条，列表区域稳定、分页控件保持可定位。
- 页码、筛选与数据对应正确；请求失败可重试；快速连续翻页时旧请求不覆盖新页。
- 浏览器回归覆盖首次请求、缓存命中与失败重试三条路径，并进入 CI。

## 设计依据

- [08 §6 工作空间总览](../../../plans/fullstack-design/08-frontend-implementation.md#6-工作空间总览页pagesoverviewindexvuev2)：列表筛选「任一变化重置 `page=1` 并把上一有效结果保留到新查询返回」，以及列表分页只改列表页码的约定。
- [V2 原型总览列表](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html)：bad case 列表与分页条作为同一张卡片的稳定区块渲染，不因翻页重建整页。

## 实现内容

- 查询层：`useOverviewCases` 使用 `placeholderData`，在同一工作空间内把上一有效的结果保留到新查询返回；跨工作空间不回退到其它空间的数据。
- 组件层：`BadCaseTable` 仅在「首次加载且没有数据」时显示骨架；已有数据时翻页或改筛选继续渲染旧行，增加 `aria-busy` 与「加载中…」提示，分页条保持可见与可操作。
- 数据层：翻页仍由 URL `page` 驱动，查询键按页隔离，旧请求完成后只写回自己的缓存键，不会覆盖新页。
- 测试：组件单测覆盖骨架只用于首次加载、加载中保留旧行与分页条；页级单测覆盖翻页占位数据；E2E 用三页合成数据、延迟响应与失败注入覆盖首次请求、缓存命中与失败重试，断言滚动位置不跳顶且无 document 重载。
- 文档：实现时按实际行为补齐 `08 §6.2` 的列表加载说明，并在 Agent Note 记录根因与取舍。

## 实施步骤

1. 准备至少三页合成 bad case，滚动到列表底部，首次访问第 2、3 页并观察滚动位置、列表高度与加载态。
2. 让列表加载态保留上一有效结果与分页条，记录首次请求、缓存命中两条路径的滚动位置。
3. 补组件单测、页级单测与浏览器回归；覆盖末页不足一页、失败重试与快速连续翻页。
4. 运行聚焦 E2E、前端单测、类型与 lint、文档与流程门禁，并更新设计文档与 Agent Note。

## 依赖与交付边界

- 无阻塞依赖；范围限总览 bad case 列表的加载与分页表现及其回归，不改 API、契约、数据语义、分页大小或排序。
- 不重设计总览、不改变全局时间/来源筛选与列表筛选的既有解耦，不改工作空间壳层的滚动归属。

## 独立验证

```sh
pnpm test:e2e -- --pattern overview
pnpm --filter @harness/web test
pnpm typecheck:web
pnpm lint:web
pnpm verify:flow
```

- 至少三页合成数据、1500×837 视口：在列表底部首次点击「下一页」，请求前、加载中、完成后 `scrollTop` 均大于 0 且不跳回顶部，不产生 document 重载。
- 返回已访问页再翻页时列表立即显示缓存数据，滚动位置同样保持。
- 末页不足一页、请求失败后重试、快速连续翻页均得到正确页码与数据。
- 聚焦 E2E、前端单测、类型、lint 与流程门禁通过。

## 验收标准

- 未访问页和已访问页均不触发整页刷新或滚动跳顶。
- 加载期间保持列表区域稳定，上一有效行与分页控件保持可见。
- 页码、筛选、数据对应正确；失败可重试，旧请求不覆盖新页。
- 浏览器回归覆盖首次请求、缓存命中与失败重试三条路径，并进入 CI。

## 门禁与 CI

- 运行聚焦浏览器回归、前端单测（覆盖率不低于 80%）、类型与 lint，以及 `verify:docs`、`verify:flow`。
- 新增 E2E 随现有 e2e lane 进入 CI；不新增独立 workflow。

## 非目标

- 不重设计总览，不改变排序、分页大小、统计口径或服务端缓存。
- 不修改 API 与 contracts，不引入新的分页或滚动库。
- 不为掩盖症状而隐藏分页控件或移除骨架屏的首次加载用途。
