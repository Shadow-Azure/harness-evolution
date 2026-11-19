# 单个进化对象分析版本行显示 digest，应按 V2 原型显示 tag 或 commit id

[English](m17-target-version-ref-labels.en.md) | 中文

```yaml flow
kind: issue
id: m17-01
milestone: m17
depends: []
priority: P2
status: in-progress
scope:
  - apps/api/app/service/overview/**
  - apps/api/app/db/crud/**
  - apps/api/app/service/evolution/**
  - apps/api/tests/**
  - apps/web/src/pages/overview/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - .agents/notes/**
  - .agents/flow/**
  - docs/**
  - scripts/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-19-target-version-ref-labels.md
github:
  number: 389
  url: https://github.com/Shadow-Azure/harness-evolution/issues/389
```

## 背景

2026-11-19 生产反馈：总览 → 进化对象总览 →「单个进化对象分析」→「潜在 bad case 分布」里，`systematic-debugging · skill` 的版本行显示 `digest:580c97cf8ca7901…`、`digest:8e54e1438967ef9…`。这些版本实际来自 git ref，展示层却只保留了内容 digest；V2 原型同一区域显示 `ref + 短 commit`。生产截图、红框放大与原型对照见 [issue #389](https://github.com/Shadow-Azure/harness-evolution/issues/389)。

根因在对象总览的版本发现：`agent_events.object_version` 与 `object_revision` 被分别当作独立版本，同一触发记录里的 `main` 与 `digest:8e54…` 会拆成两行；`TargetDetailVersion` 只暴露 `version`，前端没有 ref / commit 可用。`evolution_runs` 同时保存 `target_version`（ref）与 `target_revision`（digest）及 `base_commit`，但对象卡读取路径没有利用。

## 目标

- 版本来自 tag、分支或 commit id 时，版本行与版本多选显示该 ref；有 run 记录时同时显示短 commit。
- 同一触发记录同时给出 ref 与 digest 时合并为一行，优先 ref，不重复计数。
- 只有 digest 证据的历史版本保留 digest 兜底，页面不空白、不丢版本计数。
- 版本筛选、覆盖版本数、潜在 / 去重统计与 Session 关联、归因、缓存键口径不变。

## 设计依据

- [15 §9.2 对象 revision 与模型身份](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md#92-对象-revision-与模型身份)：`targetVersion` 是用户选择的 ref，`targetRevision=digest:<sha256>` 用于关联、匹配与缓存；选中的 ref 保留为版本/显示与代码基线。
- [05 §4.18 总览与空间 Session 列表](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2)：对象总览与详情契约的宿主章节。
- [V2 原型](../../../plans/ui-prototype-v2/harness-evolution.html)：`v2TargetVersions()` 与 `v2TargetDetailCard()` 将版本建模为 `{ref, commit, date}`，版本行与多选渲染 `ref + commit`。
- Agent Note：[2026-11-19-target-version-ref-labels](../../notes/implemented/bug-fix/2026-11-19-target-version-ref-labels.md)。

## 实现内容

**版本聚合**

- 对象总览版本发现从“每个 `object_version` / `object_revision` 各算一个版本”改为按触发记录聚合：同一记录的 ref 与 digest 是同一版本的两个身份；digest 作为匹配与筛选规范键，ref 作为展示主标签。
- 同一 digest 对应多个 ref 时，展示 ref 按最近一次 run 的 `target_version`、否则 `defaultRef`、否则自然序优先；跨记录相同 digest 合并。
- 只有 digest 证据的记录不反查 git ref，保留 digest；只有 ref 的旧记录保持 ref 版本。

**run 证据**

- 对象总览仓库新增按 workspace + 对象读取 `evolution_runs` 的只读查询；用 `target_revision`（优先）或 `target_version` 关联 `base_commit`，取短 commit；默认 ref 与 digest 只有 run 关联时也按 run 的 ref↔digest 证据合并；查询有界，不写库。

**契约与前端**

- `TargetOverviewItem` / `TargetDetailTarget` 增加 `versionOptions: [{version, ref, commit}]`；`TargetDetailVersion` 增加可空 `ref` / `commit`；`versions` 仍是筛选规范键。
- `TargetDetailCard` 的版本多选与版本行按原型渲染 ref + 浅色短 commit；digest 兜底照常显示；复选框值、URL 与统计仍使用规范键。
- `TargetSideList` 的主版本标签同步使用 ref。

**测试与文档**

- API 单测覆盖 ref+digest 合并、run commit、digest 兜底、多 ref 优先级与筛选兼容；组件测试覆盖多选/版本行渲染；真实浏览器冒烟覆盖对象卡显示与筛选。
- 更新 Agent Note 与设计文档中的对象卡版本展示约定；Before / After 截图放 PR 描述，不提交仓库。

## 实施步骤

1. 在 `db/crud/overview_targets.py` 增加 run 版本证据查询与记录类型。
2. 在 `service/overview/targets.py` 聚合 ref/digest 身份、回填 run commit，并扩展 `TargetAnalysis`。
3. 更新 `target_schemas.py` 与 contracts，运行 `pnpm contract:generate`。
4. 更新 `TargetDetailCard.vue`、`TargetSideList.vue` 及组件测试。
5. 补 API 单测、真实浏览器冒烟与 Agent Note，跑聚焦门禁。
6. 采集同场景 Before / After 截图并写入 PR 描述。

## 依赖与交付边界

- 依赖：无。只读现有 `agent_events` / `evolution_runs` 数据，不需要额外资源或凭据。
- 非目标：不改变 `PotentialMatcher`、归因缓存键、Session 关联或 probe 口径；不为只有 digest 的历史版本反查 git ref；不改对象卡其它区块与版本筛选交互。

## 独立验证

```sh
pnpm test:api -- tests/m11-03-target-overview
pnpm test:web -- --run apps/web/src/pages/overview
pnpm test:e2e -- m11-04
pnpm contract:check
pnpm typecheck:api
pnpm typecheck:web
```

- ref+digest 同记录时 `versions` 只有一个规范键，`versionOptions` 给出 ref，`byVersion` 只有一行且不重复计数。
- 有 run 记录时 `TargetDetailVersion.commit` 为短 commit；只有 digest 时保持 digest 且计数不丢。
- 页面版本多选与版本行显示 ref + commit；筛选后的统计与改动前一致。

## 验收标准

- 同态数据（`main` / `v6.4.1` 与对应 digest）下，对象卡版本行与多选显示 ref，不再出现长 digest；有 run 时带出短 commit。
- 只有 digest 证据的历史版本仍然可见；页面不空白、不丢版本计数。
- 版本选择、筛选后的分布、覆盖版本数、去重统计与 Session 关联、归因、缓存键口径不变。
- Before / After 截图与 V2 原型同区域对照；PR 描述包含证据。

## 门禁与 CI

- `pnpm contract:check`、`pnpm typecheck:api`、`pnpm typecheck:web`、`pnpm lint:api`、`pnpm lint:web`、`pnpm test:api`、`pnpm test:web`、`pnpm test:e2e`、`pnpm lint:docs`、`pnpm verify:flow`。
- 新增测试覆盖 ref/digest 合并、run commit、digest 兜底和前端渲染。
- PR 标题与提交标题引用本 issue 的 GitHub 编号。

## 非目标

- 不重构版本匹配与归因管线，不改变 `digest:<sha256>` 作为唯一身份的口径。
- 不为历史 digest 补解析 git ref，不引入新的版本数据源或迁移。
- 不改变版本多选的交互、默认最近 N 个或 `versionLimit` 语义。
