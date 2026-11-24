# 运行详情迭代步骤的来源 bad case 标题显示短标题

[English](bugfix-iteration-source-short-title.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-47
milestone: bugfix
depends:
  - m21-01
priority: P2
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - tests/e2e/**
  - plans/**
  - .agents/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 570
  url: https://github.com/Shadow-Azure/harness-evolution/issues/570
```

## 背景

生产「自进化 → 运行详情 → 第 6 步 迭代优化」的来源 bad case 表把归因报告摘要当标题渲染：本 run 20 条，单条 422–1541 字符、平均 795，每行被撑成多段长文，object_name、类型、触发点与上报时间被挤到右侧，无法逐行核对本轮覆盖的 case；第 5 步「聚类与严重度」复用同一投影，问题相同。生产 `bad-cases/{id}` 返回的 `title` 是 47 字符短标题、`reason` 才是长正文，说明两级文本在数据里本来就分得开，是投影取错了字段。

根因在 `apps/api/app/service/evolution/stages.py` 的 `_cluster_cases()`：V2 分支取 `attribution_by_case[bad_case_id].probe_description`，legacy 分支取 `row.probe_description`，都把归因摘要写进 `StepClusterCase.title`；`_RunFacts` 只加载 candidate、attribution 与 probe，从未读取 `bad_cases.title`，所以投影只能拿摘要充当标题。`git log -S "title=row.probe_description"` 指向 #299，七步投影自引入起就是这样，不是后续回归。

## 目标

- 第 6 步「来源 bad case」表「标题」列显示来源 bad case 的短标题（`bad_cases.title`），与 V2 原型一致。
- 第 5 步「聚类与严重度」的来源表同步恢复短标题。
- 第 4 步「对象归因」的「问题现象/描述」列继续显示归因长文，不受影响。
- 不新增契约字段、不改前端组件、不要求历史 run 重新准备。

## 设计依据

- [05 §3.4 问题（bad_case）、归因状态与 probe](../../../plans/fullstack-design/05-api-design.md#34-问题bad_case归因状态与-probe)：`title` 是上报必填的短标题，`reason` 是描述正文，DB 列映射 `title ↔ bad_cases.title`。
- [05 §3.6 七步产出（七个独立端点）](../../../plans/fullstack-design/05-api-design.md#36-七步产出七个独立端点)：`clusters[].cases[]` 字段为 `badCaseId/title/objectName/badCaseType/triggerAt/createdAt`，簇标题取簇内最高频 bad case 的 `title`。
- [08 §10.3 Step6 迭代卡](../../../plans/fullstack-design/08-frontend-implementation.md#103-step6-迭代卡)：展开内容第一段是簇内来源 bad case 列表。
- [V2 原型](../../../plans/ui-prototype-v2/harness-evolution.html) 的 `evCaseTable()`：来源表「标题」列渲染 `x.title`，`detail` 不进入该列。
- [issue #165](https://github.com/Shadow-Azure/harness-evolution/issues/165)：短标题与描述正文两级文本的既定设计。
- [issue #444](https://github.com/Shadow-Azure/harness-evolution/issues/444)：同类「数据通路已有短字段但投影丢字段」的修复先例。

## 实现内容

- `apps/api/app/db/crud/bad_cases.py`：新增按 `bad_case_id` 批量读取 `title` 的只读方法，单条 `IN` 查询，不新增表或迁移。
- `apps/api/app/service/evolution/stages.py`：`_RunFacts` 增加 case 标题映射，`_facts()` 对本次 run 涉及的 case 批量取一次标题，覆盖 candidate 与 legacy probe 两条路径。
- `apps/api/app/service/evolution/stages.py`：`_cluster_cases()` 的 V2 与 legacy 分支统一使用短标题；异常缺失时回退 `bad_case_id`，不再回落到 `probe_description`；`probe_description` 只保留在第 4 步 `StepAttributionRow.description` 的既有用途。
- `apps/api/app/main.py`：把 bad case 只读仓库注入 `EvolutionStageService`。
- 测试：构造「短 `bad_cases.title` + 超长 `probe_description`」的 V2 与 legacy run，断言 `steps/clusters` 与 `steps/iteration` 的 `cases[].title` 等于短标题，且 `steps/attribution` 的 `rows[].description` 仍是长文。
- 新增 Agent Note 记录「标题 / 描述」两级文本在七步投影里的边界。

## 实施步骤

1. 补 `bad_cases.title` 批量读取方法，把标题映射接进 `_RunFacts`。
2. 修改 `_cluster_cases()` 的两条分支并补缺失保护。
3. 补 V2 与 legacy 两条投影路径的回归测试。
4. 本地起服务用同构数据核对第 5/6 步来源表与第 4 步描述。
5. 新增 Agent Note，跑门禁并提交 PR。

## 依赖与交付边界

- 依赖：m21-01
- 交付边界：只改第 5/6 步来源 bad case 的 `title` 数据来源与对应测试；不改归因摘要生成、聚类算法、契约字段或历史快照。

## 独立验证

```sh
apps/api/.venv/bin/python -m pytest apps/api/tests/evolution -q
pnpm contract:check
pnpm typecheck:api
pnpm verify:flow
```

- `steps/clusters` 与 `steps/iteration` 的 `cases[].title` 等于 `bad_cases.title`（生产样例 47 字符），不再是 422–1541 字符的归因摘要。
- `steps/attribution` 的 `rows[].description` 仍等于归因摘要，证明两级文本没有被混用。
- `pnpm contract:check` 无 diff，说明契约未被改动。

## 验收标准

- 第 6 步第 1 轮「来源 bad case」表标题列显示 47 字符短标题（如 `[SWE-bench] astropy__astropy-13236 · unresolved`），不再显示归因分析正文。
- 第 5 步「聚类与严重度」展开后的来源表同样显示短标题。
- 第 4 步「对象归因」的「问题现象/描述」列仍显示完整归因摘要。
- 契约无变化，历史 run 不重新准备也能正常渲染。
- 新增测试覆盖 V2 与 legacy 两条投影路径。

## 门禁与 CI

- `pnpm test:api`、`pnpm typecheck:api`、`pnpm contract:check`、`pnpm verify:flow`、`pnpm verify:docs`。
- PR 标题与提交标题引用本 issue 的 GitHub 编号。

## 非目标

- 不新增 `StepClusterCase` 字段，不改 OpenAPI 或生成类型。
- 不用 CSS 截断、`line-clamp` 或「取前 N 个字符」掩盖长文本。
- 不改归因摘要 `probe_description` 的生成、缓存或第 4 步展示。
- 不改簇标题算法、簇描述、严重程度或聚类过程。
- 不处理 `bad_cases.title` 本身异常过长的存量数据。
