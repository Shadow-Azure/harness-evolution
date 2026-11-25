# 第 6 步 edit patch 把整文件覆盖内容当 diff 着色

[English](bugfix-62-iteration-patch-diff.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-62
milestone: bugfix
depends:
  - bugfix-21
  - bugfix-27
priority: P2
status: ready
scope:
  - apps/api/app/service/evolution/**
  - apps/api/tests/**
  - apps/web/src/pages/evolution/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 617
  url: https://github.com/Shadow-Azure/harness-evolution/issues/617
```

## 背景

### 问题场景

2026-11-25 19:36（CST），admin 打开生产运行 `01M8957ATHZX4K48K9PGXSVSVK` 的第 6 步，展开第 4 轮（簇 `01M895G2RYCDA4M6XG5WC53QVX`，已接纳 85.0 对 80.0）。「生成的 patch（current → candidate）」显示 478 行，其中 147 行被标成红色删除、0 行标成新增、331 行按上下文展示；被标红的行以 YAML front matter 分隔符 `---` 和 Markdown 无序列表 `- **所有模式**…` 开头。

同一轮 `candidate_committed` 事件里的真实 `unifiedDiff`（落库于 `round.patch` 之外的执行日志）是 72 行新增、0 行删除；目标文件从 406 行增长到 478 行，第 1 至第 4 轮都没有发生过整文件回退。页面展示的不是 diff，而是 agent-edit 轮次落库的整文件覆盖内容。

### 分析

- `#488` 之后，agent-edit 的 `round.patch` 落库形状是 `files[] / note / intent / report`（单文件另带 legacy `file / lines / overwrite`）；`files[].lines` 是应用 EditPlan 后的**整文件**行。
- `#522` 修好了读取这个形状时的 500，但 `StepRoundPatch` 仍没有 diff 字段；`DiffView.vue` 继续按行首 `+` / `-` / `@@` 给 `files[].lines` 着色。Markdown 列表与 `---` 于是命中 `startsWith("-")`，被渲染成删除。
- `intent`、`report` 与 candidate 的真实 `unifiedDiff` 都已经存在，只是没有进入第 6 步读模型；测试也只用人工构造的 `-old / +new` 行，未覆盖真实整文件输出。

## 目标

- 第 6 步只展示真实变更片段，不再把整文件中的 Markdown 列表或 front matter 分隔符当成删除行。
- 新轮次从落库数据即可拿到真实 diff；历史轮次在没有 diff 时安全降级，不产生红色删除误报。
- 前后端对 `patch.diff` / `patch.files` 的语义有唯一契约，并由回归测试锁住。
- 保留第 6 步现有 patch / candidate / push / eval / 接纳结构，不改评测与 git 行为。

## 设计依据

- [05 §3.6](../../../plans/fullstack-design/05-api-design.md)：`steps/iteration` 的 `rounds[]` 契约与 patch 投影规则。
- [08 §10.3](../../../plans/fullstack-design/08-frontend-implementation.md)：第 6 步 patch / candidate / push / eval / 接纳的渲染结构。
- [07 §5.5.4](../../../plans/fullstack-design/07-backend-implementation.md)：agent-edit 的只读探索、EditPlan 应用与 intent / diff 审计。
- [`bugfix-27`](bugfix-iteration-patch-read.md) 与 [`bugfix-21`](bugfix-agent-edit-iteration.md)：本轮读取模型与 agent-edit 落库结构的前置事实。

## 实现内容

- `apps/api/app/service/evolution/git_candidate.py`：candidate commit 成功后把真实 `unified_diff` 回写 `round.patch.diff`；`_stored_patch()` 也能序列化 `PatchBundle.unified_diff`。
- `apps/api/app/service/evolution/round_patch.py`：`stored_bundle()` 读回 `diff`，旧格式仍兼容。
- `apps/api/app/service/evolution/stages.py`：`StepRoundPatch.diff: list[str] | null`；优先投影落库 diff，缺失时按 `intent` + `report.status == "applied"` 合成变更块，仍缺失返回 `null`。
- `apps/web/src/pages/evolution/components/DiffView.vue`：有 `diff` 时按文件块渲染真实 unified diff，文件头行不参与增删计数；`diff` 为 `null` 时显示中性整文件预览，不做 `+` / `-` / `@@` 分类。
- `packages/contracts`、`apps/api/tests`、`apps/web/src/**/*.test.ts`、`tests/e2e`、`plans/fullstack-design/05-api-design.md`、`plans/fullstack-design/08-frontend-implementation.md`：契约、回归测试、E2E fixture 与设计文档同步。

## 实施步骤

1. 写侧落库 diff，并用单测固定 `_stored_patch()` → `stored_bundle()` 的往返。
2. 读侧投影 `diff`，补 intent/report 回退与无 diff 的 `null` 分支。
3. 前端改为 diff 优先、整文件回退中性化，补 `---` 与 Markdown 列表的回归用例。
4. 更新 OpenAPI 契约、设计文档与 E2E fixture，跑聚焦门禁。
5. 部署后在 `01M8957ATHZX4K48K9PGXSVSVK` 第 4 轮复核红色删除行归零。

## 依赖与交付边界

- 依赖：`bugfix-21`（agent-edit 落库 intent / diff 的能力）与 `bugfix-27`（patch 读取模型）。
- 交付边界：只改第 6 步 patch 的持久化、读取、渲染与测试；不重算 git diff，不改 patch 生成、聚类、评测和推送。
- 历史轮次不做数据迁移：通过 `intent` / `report` 回退展示；没有可用数据的轮次显示整文件中性预览，不伪造 diff。

## 独立验证

```sh
pnpm test:api tests/evolution/test_iteration_round_patch.py
pnpm test:api tests/m5-11-evolution-recovery/test_full_placeholder_loop.py
pnpm test:web
pnpm typecheck:web
pnpm contract:check
pnpm test:e2e --pattern m10-06
pnpm verify:flow
```

- 预期：新轮次 `patch.diff` 来自落库 `candidate.unifiedDiff`；历史轮次 `patch.diff` 为 applied 编辑合成的变更块；无 diff 且无 intent 时为 `null`；页面第 4 轮不再出现红色 `---` 或 `- **所有模式**`。

## 验收标准

- 第 4 轮页面展示真实 diff 或与簇对应的变更块，红色删除误报归零。
- 新轮次的 `patch.diff` 来自落库的 `candidate.unifiedDiff`；历史轮次通过 `intent` / `report` 展示变更块，或降级为无着色的整文件预览。
- 测试覆盖真实落库输出中的 `---`、`- ` 行，确保不会被判为删除；同时覆盖无 intent / 无 diff 的轮次。
- 契约、设计文档与 E2E 证据同步更新，CI 全绿。

## 门禁与 CI

- `pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api`、`pnpm test`、`pnpm typecheck:web`、`pnpm contract:check`、`pnpm test:e2e --pattern m10-06`、`pnpm verify:flow`、`pnpm verify:docs`。
- 提交与 PR 标题带 `(#617)`。

## 非目标

- 不改 `cluster.review` / `cluster.score` 的聚类或描述生成，也不改 `cluster_probe.description` 的格式。
- 不改 patch 生成策略、`EDIT_BUDGET`、`MAX_CONTENT_LINES` 或 agent 工具面。
- 不改评测、推送、candidate 状态机与最终 commit message。
- 不做历史 round 的批量数据迁移，也不重写已接纳轮次的落库内容。
