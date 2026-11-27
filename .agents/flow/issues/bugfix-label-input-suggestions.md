# 空间 label 输入基于现有 catalog label 自动补全

[English](bugfix-label-input-suggestions.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-68
milestone: bugfix
depends:
  - bugfix-60
priority: P2
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - docs/**
  - .agents/**
adr: []
github:
  number: 629
  url: https://github.com/Shadow-Azure/harness-evolution/issues/629
```

## 背景

「空间管理 → Badcase 类型」页签当前只有一个纯文本输入框，空间管理员必须凭记忆输入公共目录的 label 全称。label 区分大小写、精确匹配，输错一个字符就等于一条规则失效且没有任何反馈；同时新环境里管理员也无从知道公共仓库当前存在哪些 label。数据面已经有 `bad_cases.catalog_label` 投影列（#582），完全可以作为候选词来源。

## 目标

为 `Badcase 类型` 的输入框提供**基于当前 `bad_cases.catalog_label` 的候选下拉**：输入时按前缀过滤，聚焦时可看到公共目录里出现最多的 label，选中即加入待保存草稿；仍允许手动输入尚未同步到本地的 label。

## 设计依据

- [17 · 公共 badcase 按 label 划分工作空间 §6 API / §7 空间管理 UI](../../../plans/fullstack-design/17-workspace-bad-case-label-routing.md)
- [05 接口设计](../../../plans/fullstack-design/05-api-design.md)：工作空间前缀端点、viewer/member 读边界
- [17 §2.3]：`catalog_label` 是 `meta_data.label` 的查询投影，不是第二事实源；候选只读该列。

## 问题描述、分析过程与根因

1. 输入框无任何候选：`BadCaseLabelsTab.vue` 仅有 `input` + 「添加」按钮，label 只能人工输入。
2. 现有数据面已具备候选来源：`bad_cases.catalog_label` 为同步时投影的可空列，`ix_bad_cases_catalog_label` 已建索引，`SELECT DISTINCT` 与 `LIKE 'prefix%'` 均可走索引，SQLite/MySQL 行为一致。
3. 前端拿不到候选：`GET /api/workspaces/{wid}/bad-case-labels` 只返回该空间已配置项与计数，没有词表端点；`contracts` 也没有对应类型。
4. 不能前端自行收集：拉取全部 badcase 只为取 label 又重又跨空间；用其他空间的规则集合当候选会泄露「别的空间在订阅什么」。

根因：缺少一个只读、轻量的 label 词表端点，以及输入控件没有接远端候选的能力。

## 实现内容

唯一推荐方案：新增一个只读候选端点 + 把输入框换成远端自动补全控件；保存语义（完整集合替换）不变。

- **API**：`GET /api/workspaces/{wid}/bad-case-labels/suggestions?q=<prefix>&limit=<n>`，`require_workspace_role("viewer")`，返回 `{ "items": [ { "label": "review", "badCaseCount": 12 } ] }`。
  - 数据源：`SELECT catalog_label, COUNT(*) FROM bad_cases WHERE catalog_label IS NOT NULL [AND catalog_label LIKE :escaped_prefix || '%'] GROUP BY catalog_label ORDER BY count DESC, label ASC LIMIT :limit`。
  - 参数：`q` 可选、最长 128；`limit` 1–50，默认 20；`%`/`_` 按字面量转义（沿用会话搜索的转义方式）。空 `q` 返回出现次数最多的前 N 个。
  - 为什么挂 workspace 前缀：复用既有 `viewer` 鉴权与 404 语义；候选是公共目录词表，**不按当前空间可见性收窄**（配置 label 前该空间本就看不到任何 case），也不读取任何其他空间的规则集合。
- **前端**：`BadCaseLabelsTab.vue` 用 `el-autocomplete`（已在 `test/setup` 注册）替换纯 `input`：
  - 远端 `fetch-suggestions`（200ms debounce），`value-key="label"`，展示 `label · N 条`；
  - 保留自由输入（新 label 可能尚未同步到本地），禁用 `select-when-unmatched` 的隐式行为；
  - 已配置/重复 label 从候选里过滤掉；选中只加入草稿（不保存），「添加」按钮与 Enter 行为不变；
  - 候选接口失败时降级为纯手输，不阻塞保存；loading 态不影响已输入内容。
- **契约**：新增 `WorkspaceBadCaseLabelSuggestion`、`WorkspaceBadCaseLabelSuggestionListResponse`，`pnpm contract:generate` 后进 `packages/contracts`。
- **文档**：设计 17 §6 增加端点、§7 增加下拉交互；更新 Agent Note `2026-11-24-workspace-bad-case-label-routing` 的 API/UI 段并重录 i18n。

## 实施步骤

1. 先写失败测试：API 用例覆盖 DISTINCT、前缀过滤、`limit` 边界、空 `q` 按计数排序、`NULL` 排除、viewer 可读 / 未认证 401、非法 `limit` 422；组件用例覆盖候选渲染、选中加入草稿、自由输入、已配置去重、接口失败降级。
2. 实现 repository 查询（复用 `bad_cases` 索引）与 service、路由、Pydantic 响应模型。
3. `pnpm contract:generate`；前端加 `listWorkspaceBadCaseLabelSuggestions` API + 组合式函数（挂在 `adminBadCaseLabels` 前缀下便于失效）。
4. 把输入框换成 `el-autocomplete`，接通 debounce、过滤、降级；补组件测试。
5. 同步原型 `plans/ui-prototype-v2/harness-evolution.html` 的下拉形态；更新设计 17 与 Agent Note。

## 依赖与交付边界

- 依赖：`bugfix-60`（#582，已实现 `catalog_label` 投影与 label 配置链路）为语义前提；本 issue 不改保存/重算事务。
- 交付边界：只读候选 + 输入控件；不改 label 匹配规则、不改同步流程、不引入 label 字典表。
- 非目标：不做「label 管理 / 重命名 / 删除」后台；不做全文模糊搜索（仅前缀）；不按 label 展示跨空间 case 数。

## 独立验证

```sh
cd apps/api && .venv\Scripts\python.exe -m pytest tests/workspaces/test_bad_case_labels_api.py -q
pnpm --filter @harness/web exec vitest run src/pages/workspaces/components/BadCaseLabelsTab.test.ts
pnpm contract:check && pnpm typecheck && pnpm lint:api && pnpm lint:web
```

- 构造 3 条 `catalog_label`（`review`×2、`tool-use`×1、`NULL`×1），`GET .../suggestions` 返回 `[review(2), tool-use(1)]`；`?q=rev` 只返回 `review`；`?limit=1` 只返回 `review`；未认证 401。
- 界面：聚焦输入框出现候选；输入前缀实时过滤；选中加入 chip 且不落库（按钮点亮）；手输未收录 label 仍可添加；保存后计数按完整集合重算。

## 验收标准

- 候选端点只返回非空 `catalog_label`，按出现次数降序、同数按字典序，支持前缀与 `limit`，viewer 可读且未认证被拒。
- 输入框有候选下拉且不阻塞自由输入；选中不自动保存；已配置 label 不出现在候选中。
- 候选接口异常时页面仍可手动添加与保存。
- 保存后的历史重算、计数与空间隔离行为与现状一致。

## 门禁与 CI

- `pnpm contract:generate` / `contract:check`、`pnpm typecheck`、`pnpm typecheck:web`、`pnpm lint:api`、`pnpm lint:web`、`pnpm test:api`（聚焦新增用例）、`pnpm test:web`。
- 文档：`pnpm record:i18n -- plans/ui-prototype-v2 相关段落`（如改原型的双语说明则重录对应配对）、`pnpm lint:docs`、`pnpm verify:flow`。
- CI 纳入新增用例，覆盖率不低于 80%。

## 非目标

- 不建立 label 字典或管理页面，不推断/补全缺失 label。
- 不改变 label 的精确匹配语义（候选只是提示，不是约束）。
- 不提供跨空间的 label 订阅关系可见性。
