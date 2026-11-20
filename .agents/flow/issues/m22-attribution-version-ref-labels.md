# 归因列表版本显示 digest，应显示 tag / commit 并支持截断复制

[English](m22-attribution-version-ref-labels.en.md) | 中文

```yaml flow
kind: issue
id: m22-01
milestone: m22
depends:
  - m17-01
priority: P2
status: done
scope:
  - plans/**
  - apps/api/**
  - apps/web/src/pages/errors/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - scripts/**
  - .agents/**
adr:
  - ../../notes/implemented/feature/2026-11-20-attribution-version-labels.md
github:
  number: 416
  url: https://github.com/Shadow-Azure/harness-evolution/issues/416
```

## 背景

2026-11-20 用户在生产 Session 错误查看页左侧「归因分析 · 按进化对象」看到归因项版本为 `digest:580c97cf…`（71 字符）：版本号不可收缩、无截断，挤掉对象名 `systematic-debugging`，压住「缓存 / 可归因」标签并溢出卡片。总览的版本行已按 m17（#389）显示 ref + 短 commit，但归因列表仍只读 `probe_reports.object_version`（digest），契约没有 ref / commit，也没有长值截断、完整值查看和复制入口。V2 原型默认样例使用短 tag，未暴露该问题；把同一 digest 注入原型后同样重叠，说明原型结构也未处理长版本号。

## 原型证据

**修改前 / 修改后（同一数据、同一 1500×837 @2x 视口）**

[![归因列表版本标识 Before / After](https://github.com/Shadow-Azure/harness-evolution/releases/download/attribution-version-labels-evidence-20261120/attribution-version-before-after.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/attribution-version-labels-evidence-20261120/attribution-version-before-after.png)

**修改后：悬停截断值，上方显示完整 digest**

![悬停显示完整 digest](https://github.com/Shadow-Azure/harness-evolution/releases/download/attribution-version-labels-evidence-20261120/attribution-version-tooltip.png)

**修改后：原型完整页**

![原型完整页](https://github.com/Shadow-Azure/harness-evolution/releases/download/attribution-version-labels-evidence-20261120/attribution-version-full.png)


## 目标

- 归因列表项有 ref 时显示 ref + 短 commit（与总览版本行一致）；只有 commit 时显示短 commit；只有 digest 时保留 digest 兜底。
- 长版本号截断显示；悬停或聚焦时在版本上方显示完整值；旁边提供小复制按钮，复制完整版本标识（commit 优先，digest 兜底）。
- 长版本号不挤掉对象名、不压住缓存 / 结论标签、不溢出卡片。
- 先更新 V2 原型并给出同视口 Before / After；生产 API 契约与前端按原型落地。
- 不改变归因匹配、缓存键、统计与结论语义。

## 设计依据

- [08 §7.1 错误详情页布局与数据](../../../plans/fullstack-design/08-frontend-implementation.md)：归因列表项包含结论 badge、时间、缓存标记与定位；本次补充版本标识的展示规则。
- [15 §9.2 对象 revision 与模型身份](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md#92-对象-revision-与模型身份)：`targetVersion` 是可读 ref，`targetRevision=digest:<sha256>` 用于匹配与缓存；展示层应保留 ref。
- [m17 #389 对象卡版本显示](https://github.com/Shadow-Azure/harness-evolution/issues/389)：总览版本行已按 ref + 短 commit 展示，本 issue 将同一规则延伸到归因列表。
- [V2 原型](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html)：`ErrorApp` 的归因列表与 `v2TargetDetailCard()` 的版本行。

## 实现内容

**V2 原型（本 issue 首个 PR）**

- `ErrorApp` 归因项渲染 `ref` + 短 commit；无 ref 时显示短 commit 或截断 digest。版本区可收缩并省略，复制按钮复制完整标识。
- 悬停或聚焦显示完整版本浮层；浮层挂到页面级节点，避免被 `.err-case` / `.err-list` 的 overflow 裁剪。
- 扩展原型归因数据：已知版本带 ref / commit，digest-only 历史项保留兜底；注入同一 digest 后不再重叠。

**生产 API 与前端（后续 PR）**

- `AttributionItem` 增加可空 `objectRef` / `objectCommit`（或等价版本选项），从 run 的 `target_version` / `target_revision` / `base_commit` 回填；只有 digest 时保持空并返回 digest。
- 契约更新后运行 `pnpm contract:generate`；归因列表读取路径只读现有数据，不写库、不反查 git ref。
- `AttributionItem.vue` 按原型渲染 ref + 短 commit、截断、完整值浮层与复制按钮；CSS 保证长值不压住 badge。
- 单测覆盖 ref / commit / digest 三种输入、复制与 tooltip；E2E 覆盖长 digest 下无重叠。

## 实施步骤

1. 更新 V2 原型并采集同视口 Before / After（同一注入数据），把截图放进本 issue。
2. 扩展 `AttributionItem` 契约与 API 读取，运行契约生成。
3. 更新 `AttributionItem.vue` 与样式，补组件测试。
4. 补 E2E 与 Agent Note、设计文档 08 §7.1。
5. 全量门禁通过后交付生产实现。

## 依赖与交付边界

- 依赖 m17-01（已完成）：复用 ref / 短 commit 的展示口径与 run 证据。
- 本 issue 首个 PR 只改 V2 原型、流程与 Agent Note；生产实现随后按同一 issue 推进。
- 不新增数据源，不为历史 digest 反查 ref，不改归因匹配 / 缓存 / 分页 / 统计。
- 不把生产 Session 内容或用户截图提交到仓库。

## 独立验证

```sh
pnpm verify:flow
pnpm lint:docs
```

- 原型在 1500×837 @2x 下渲染归因项：ref + 短 commit 正常；注入 71 字符 digest 后，版本截断、对象名可见、badge 不重叠；悬停显示完整 digest；复制按钮复制完整 digest。
- 生产阶段追加：`pnpm contract:check`、`pnpm typecheck:web`、`pnpm lint:web`、`pnpm test:web`、`pnpm test:e2e -- --pattern <归因列表用例>`。

## 验收标准

- 归因项有 ref 时显示 ref + 短 commit；无 ref 有 commit 时显示短 commit；只有 digest 时显示截断 digest。
- 长版本号不再挤掉对象名或压住缓存 / 结论标签，卡片不溢出。
- 悬停截断值可在其上方看到完整值；复制按钮复制完整版本标识并提示成功。
- 原型 Before / After 与 issue 截图一致；生产实现与原型同区域可比。
- 归因匹配、缓存键、分页、统计与结论语义不变。

## 门禁与 CI

- `pnpm verify:flow`、`pnpm lint:docs`；生产阶段追加 `pnpm contract:check`、`pnpm typecheck:web`、`pnpm lint:web`、`pnpm test:web`、`pnpm test:e2e`。
- PR 标题与提交标题引用本 issue 的 GitHub 编号。

## 非目标

- 不改变 `digest:<sha256>` 作为匹配与缓存规范键的口径。
- 不为只有 digest 的历史归因反查 git ref / tag。
- 不重排归因列表其它字段，不改变分页、筛选、选中和深链交互。
- 不改对象总览已完成的版本展示。

## 关闭说明

生产实现已由 [#426](https://github.com/Shadow-Azure/harness-evolution/pull/426) 合入并通过 CI；原型 PR #419 与生产 PR #426 的 Before / After、生产验证见本 issue 正文与生产证据评论。本 issue 关闭，M22 完成。
