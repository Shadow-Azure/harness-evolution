# 总览右栏置灰展示已停用的进化对象，且不参与统计

[English](bugfix-disabled-target-overview-sidebar.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-65
milestone: bugfix
depends:
  - m11-03
  - m11-04
priority: P2
status: ready
scope:
  - apps/api/app/api/overview.py
  - apps/api/app/service/overview/**
  - apps/api/app/db/crud/evolution_targets.py
  - apps/api/tests/**
  - apps/web/src/pages/overview/**
  - apps/web/src/api/**
  - apps/web/src/composables/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 626
  url: https://github.com/Shadow-Azure/harness-evolution/issues/626
```

## 背景

生产「总览 → 进化对象总览」只读取 `enabled=true` 的进化对象：`TargetOverviewService._analyses` 固定 `enabled_only=True`，`GET /api/workspaces/{wid}/overview/targets` 的 `summary` 与 `items` 也只覆盖启用对象。空间管理员把对象停用后，它会从整个总览消失——顶部统计减少、右侧「进化对象」列表不再出现，也没有入口看出该配置仍然存在、只是已停用。用户确认停用对象应当保留在右栏，但不进入其它统计。

本 Issue 只解决可见性：停用对象保留在右栏末尾，置灰并标注「已停用」，可以启用、编辑或移除；重新启用后回到正常排序与统计。停用对启动向导、绑定批次、归因与 run 的既有语义不变。

## 原型截图对照

同一 V2 原型、同一页面状态（`?u=admin&ws=ws-harness&page=overview&tab=targets`）、1500×1200 CSS 视口、2× DPR、浅色主题；数据为 `ws-harness` 合成 fixture（3 个启用对象 + 1 个停用的 `release-notes`）。点击图片可查看原尺寸。

| 修改前（当前 main 原型） | 修改后（本 Issue 原型） |
| --- | --- |
| [![修改前：右栏只有 3 个启用对象](https://github.com/Shadow-Azure/harness-evolution/releases/download/disabled-target-overview-evidence-20261126/baseline-overview-targets.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/disabled-target-overview-evidence-20261126/baseline-overview-targets.png) | [![修改后：右栏末尾置灰显示已停用的 release-notes，带启用按钮](https://github.com/Shadow-Azure/harness-evolution/releases/download/disabled-target-overview-evidence-20261126/disabled-target-overview-targets-enable.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/disabled-target-overview-evidence-20261126/disabled-target-overview-targets-enable.png) |

左图右侧只有 3 个启用对象，分页为「共 3 个」；右图在末尾增加「已停用对象」分组，`release-notes @v1.2.3` 置灰并带「已停用」徽标与「启用」按钮，顶部统计条仍为 3 个对象、18 关联 Session、31 潜在 bad case。两张图的图表、分布与单对象分析卡一致。

## 目标

- 右栏在启用对象之后展示当前空间所有已停用对象，置灰并标注「已停用」；只展示对象/版本、归因 Skill 与启用/编辑/移除入口。
- 停用对象不进入顶部统计条、趋势图、两块分布、单对象分析卡的下拉、筛选下拉与潜在 bad case 列表。
- API 单独返回停用对象的只读元数据；现有 `items`、`total`、`summary` 与所有启用对象口径保持不变。
- 重新启用后，对象回到右栏正常排序并重新进入统计。
- 用同一个原型、视口和页面状态提供修改前后截图。

## 设计依据

- [08 §6 工作空间总览](../../../plans/fullstack-design/08-frontend-implementation.md#6-工作空间总览页pagesoverviewindexvuev2)：`TargetSideList.vue` 的位置、5 条分页与对象总览布局。
- [05 §4.18 总览与空间 Session 列表](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2)：`GET /overview/targets` 的 `summary/items/total` 契约。
- [06 §5.1 进化对象配置](../../../plans/fullstack-design/06-database-design.md#51-evolution_targets--可自进化的对象配置)：`enabled=false` 的既有语义（不进入向导候选、不领取绑定批次）。
- [V2 设计 §5.3 双视角](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/design-v2.md#53-双视角bad-case--进化对象)：右侧对象列表与停用对象分组。
- [V2 原型右栏](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html)：`v2RenderTargetsOverview` 的启用列表与停用分组。

## 实现内容

- 契约：在 `packages/contracts` 新增 `TargetOverviewDisabledItem`（`targetId`、`objectType`、`objectName`、`attributionSkillName`、`defaultRef`），并在 `TargetOverviewListResponse` 增加 `disabled` 列表；`items` 与 `summary` 保持启用对象口径。运行 `pnpm contract:generate` 更新 OpenAPI 生成类型。
- API：`TargetOverviewService.list_targets` 维持现有启用对象分析与汇总；额外读取同空间 `enabled_only=False` 的记录，筛出停用对象按对象名排序写入 `disabled`。`trend`、`cases`、`detail` 继续只用启用对象，不新增端点。
- Web 数据：`useOverviewTargets` 透出 `disabled`；`TargetsOverview` 将 `disabled` 传给 `TargetSideList`，不并入 `targetItems`，因此筛选、图表、分布、详情选择器和潜在 bad case 列表都看不到停用对象。
- Web 展示：`TargetSideList` 在分页的启用对象之后追加「已停用对象」分组；每项显示对象/版本、归因 Skill 与「已停用」徽标，置灰但保留启用/编辑/移除；编辑仍打开既有对象表单。
- 启用动作：停用项提供「启用」；点击调用既有 `useEvolutionTargets().updateTarget` 提交 `enabled=true`，成功后 invalidate 总览并把对象移回启用列表；失败显示服务端错误，不做本地乐观切换。
- 测试：API 覆盖 `disabled` 返回且 `summary`/`total` 不含停用对象；组件覆盖分组顺序、徽标、不可选中、启用与编辑/移除事件；E2E 覆盖右栏出现停用对象，以及点击启用后回到启用列表且统计恢复。
- 文档：实现时同步 `08 §6` 与 `05 §4.18` 的说明；原型侧已更新 `design-v2.md §5.3`。

## 实施步骤

1. 先加契约字段与 API 测试，确认启用对象的 `summary`、`items`、`total` 不变。
2. 实现 `list_targets` 的停用对象查询与稳定排序，跑 API 与契约门禁。
3. 接入 Web 数据流与 `TargetSideList` 分组，补组件测试。
4. 接入启用/编辑/移除与重新启用路径，补 E2E 与同视口截图。
5. 更新前端设计文档，跑全仓门禁。

## 依赖与交付边界

- 依赖：m11-03（对象总览 API）、m11-04（对象总览 UI）。
- 交付边界：只增加对象总览的停用对象展示与只读元数据；不改对象配置页、启动向导、绑定批次、归因、run、权限与既有启用对象统计。
- 停用对象允许启用/编辑/移除，但不提供历史统计或详情下钻；右栏分页计数可以包含停用对象，顶部统计、图表与列表一律不含。

## 独立验证

```sh
pnpm test:api -- tests/m11-03-target-overview
pnpm --filter @harness/web exec vitest run src/pages/overview
pnpm typecheck
pnpm contract:check
pnpm test:e2e -- --pattern target-overview
pnpm verify:flow
```

- API：同一 fixture 下，`disabled` 含停用对象；`summary.targets` 与 `items` 只含启用对象；`trend`、`cases`、`detail` 不出现停用对象。
- Web：右栏末尾显示「已停用对象」分组与「已停用」徽标；筛选下拉、单对象下拉、图表和潜在 bad case 列表不含停用对象。
- 视觉：1500×1200 CSS 视口、2× DPR、浅色主题下，修改前后同一页面状态的截图可对照，统计条数值不变。

## 验收标准

- 停用对象在总览右栏可见、置灰、标注「已停用」，并可启用、编辑或移除。
- 停用对象的出现不改变顶部 6 个统计值、趋势图、两块分布、单对象分析卡、筛选选项和潜在 bad case 列表。
- 启用对象仍按可进化数量降序、每页 5 个分页；重新启用停用对象后，它回到正常排序与统计。
- API 契约包含停用对象元数据，现有客户端字段不破坏。

## 门禁与 CI

- 命中：API 单测、Web 单测、E2E、`pnpm typecheck`、`pnpm lint:web`、`pnpm contract:check`、`pnpm verify:flow`、`pnpm lint:docs` 与 CI 全量门禁。

## 非目标

- 不改变 `enabled=false` 对启动向导、绑定批次、归因与 run 的语义。
- 不提供停用对象的历史统计、详情下钻或新的筛选维度。
- 不新增 API 端点、页面、权限或批量停用/启用能力。
- 不改动对象配置页的启停开关与表单字段。
