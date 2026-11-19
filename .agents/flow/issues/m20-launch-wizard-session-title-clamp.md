# 启动向导第 2 步 Session 关联显示短标题并收窄表格

[English](m20-launch-wizard-session-title-clamp.en.md) | 中文

```yaml flow
kind: issue
id: m20-01
milestone: m20
depends:
  - m10-05
priority: P2
status: ready
scope:
  - apps/web/src/pages/evolution/**
  - apps/api/app/service/evolution/**
  - apps/api/app/db/crud/potential.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - .agents/notes/**
  - .agents/flow/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 404
  url: https://github.com/Shadow-Azure/harness-evolution/issues/404
```

## 背景

生产「启动自进化」第 2 步「Session 关联」把 Session 的首条 prompt 全文渲染进表格，长 prompt 把表格撑宽，`对象出现`、`对象触发点时间`、`该 Session 的 bad case 数` 三列被挤出弹窗；同一位置的 V2 原型用短会话名加完整 Session ID，四列同屏。产品问题与生产/原型对照证据见 [issue #402](https://github.com/Shadow-Azure/harness-evolution/issues/402)。

根因有两层：预览接口 `SessionPreviewItem` 只返回 `title`，前端拿不到会话列表已经使用的 `short`；`table.rep` 的 `white-space: nowrap` 加上没有宽度约束，使长标题参与表格宽度计算。修复要同时补上短标题数据通路和前端的截断约束，但不动 Session 关联算法、分页与统计口径。

## 目标

- 第 2 步 Session 单元格显示可读的短标签，单行截断加省略号，完整标题放进 `title` 悬停提示。
- 保留 Session 短 ID；不改首尾缩写的既有约定。
- 1440 宽视口、720 宽弹窗下 `Session`、`对象出现`、`对象触发点时间`、`该 Session 的 bad case 数` 四列同屏，长 prompt 不产生横向滚动、不遮挡其它列。
- 预览接口返回 `short`，来源是 `session_families.short_title`；`title` 继续返回完整标题供悬停。
- Session 关联算法、bad case 统计、分页和排序不变。

## 设计依据

- [05 §4.20 自进化预览与启动](../../../plans/fullstack-design/05-api-design.md#420-自进化预览与启动v2)：`preview/sessions` 的响应字段与分页口径。
- [08 §9.2 四步表单与预览](../../../plans/fullstack-design/08-frontend-implementation.md#92-四步表单与预览)：第 2 步表格列与「Session 标题」展示约定。
- [V2 原型](../../../plans/ui-prototype-v2/harness-evolution.html)：第 2 步行使用 `a.sess.short` 加完整 `a.sid`，`.cell-sub` 有最大宽度与省略号。

## 实现内容

- `apps/api/app/service/evolution/potential.py`：`AssociatedSession` 与 `SessionPreviewItem` 增加 `short`，取自 `SessionRecord.short_title`；关联算法保持不变。
- `packages/contracts`：用 `pnpm contract:generate` 更新 `openapi.json` 与生成的 TypeScript 类型，不手改。
- `apps/web/src/pages/evolution/components/LaunchWizard.vue`：Session 标题使用 `item.short || item.title`，加 `title` 属性展示全文；会话表格改为固定布局并约束标题列，标题单行省略，空态与其它列语义不变。
- 测试：API 预览测试断言 `short` 字段；组件测试覆盖长标题被截断且悬停提示保留全文；E2E 断言第 2 步四列表头都在弹窗内且表格没有横向溢出。
- 文档：设计文档 05/08 补充 `short` 字段与截断约定；新增 Agent Note 记录「短标题数据通路 + 展示层截断」的取舍。

## 实施步骤

1. 扩展预览 DTO 与关联结果，补 API 单元测试。
2. 运行 `pnpm contract:generate` 并提交契约变更。
3. 调整 `LaunchWizard.vue` 的 Session 单元格与表格布局，补组件测试。
4. 在 m10-05 E2E seed 中加入长 prompt 标题，断言四列可见、无横向溢出。
5. 更新设计文档、Agent Note 与流程 issue，运行门禁和真实浏览器冒烟。

## 依赖与交付边界

- 依赖：m10-05
- 交付边界：只修第 2 步 Session 单元格与表格横向布局；条件条 chip、统计行口径、Session ID 展示格式、触发点列与分页行为保持现状。

## 独立验证

```sh
pnpm contract:check
apps/api/.venv/bin/python -m pytest apps/api/tests/m10-02-potential-matcher/test_preview_api.py apps/api/tests/test_openapi.py
pnpm test:web -- LaunchWizard
pnpm lint:web && pnpm typecheck:web
pnpm test:e2e -- --pattern m10-05
pnpm test:gates && pnpm verify:docs && pnpm verify:flow
```

- 预览响应包含 `short`，且与 `session_families.short_title` 一致。
- 长标题下四列表头均在弹窗可视范围内，表格 `scrollWidth` 不大于容器 `clientWidth`。
- 标题显示省略号，悬停文本等于完整 `title`。

## 验收标准

- 1440 宽视口打开第 2 步，长 prompt Session 不撑宽表格，四列同屏可见。
- 短标签、完整标题悬停提示和 Session 短 ID 同时存在。
- 关联 Session 数、分页、排序、跳过与版本未知统计不变。
- 组件测试与 E2E 覆盖长标题回归。

## 门禁与 CI

- 命中 `pnpm contract:check`、`pnpm lint:web`、`pnpm typecheck:web`、`pnpm test:web`、`pnpm test:api`、`pnpm test:e2e`、`pnpm test:gates`、`pnpm verify:docs`、`pnpm verify:flow`。
- PR 标题与提交标题引用本 issue 编号，并在 PR 描述引用产品 issue #402。

## 非目标

- 不改 `session_families.short_title` 的生成算法，也不改 Session 关联、bad case 统计或分页。
- 不对齐条件条 chip、统计行项数或完整 UUID 展示；这些差异仍在产品 issue 中记录。
- 不把生产 Session 内容或截图提交进仓库。
