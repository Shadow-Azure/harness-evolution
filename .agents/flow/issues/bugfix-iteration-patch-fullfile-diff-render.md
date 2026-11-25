# 自进化第 6 步 edit patch 大面积「删除」：整文件覆盖内容被当 diff 着色

[English](bugfix-iteration-patch-fullfile-diff-render.en.md) | 中文

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
  - apps/web/src/pages/evolution/**
  - packages/contracts/**
  - apps/api/tests/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 617
  url: https://github.com/Shadow-Azure/harness-evolution/issues/617
```

## 背景

第 6 步「迭代优化」是自进化唯一能核对「改了什么、为什么改、评测涨了多少、最终 commit 是什么」的步骤。`#522`（bugfix-27）修好了这一步的读取 500：`round.patch` 的落库结构已从单文件 `file / lines / note` 扩为 `files[] / note / intent / report`，读取侧先还原 bundle 再投影成 `StepRoundPatch`。

读取链路修好后，渲染链路仍假定 `files[].lines` 是带 `+` / `-` / `@@` 前缀的 unified diff。`DiffView.vue` 只按行首字符着色，而 agent-edit 轮次的 `lines` 是整文件覆盖后的全文。2026-11-25 19:36（CST），admin 打开生产运行 `01M8957ATHZX4K48K9PGXSVSVK` 的第 6 步，第 4 轮 patch 区域因此出现大面积红色「删除」。同一位置的真实变更由 72 行新增、0 行删除组成。

## 问题描述

### 页面现象

生产页面为 `http://8.149.232.63/workspaces/01M7KJ05ENF9784GPBDV544VB0/evolution/runs/01M8957ATHZX4K48K9PGXSVSVK?step=iteration`。第 4 轮簇为 `01M895G2RYCDA4M6XG5WC53QVX`（「prompt 类问题 · 需求未逐条落成可执行验收，覆盖度未被核对」），状态是已接纳（85.0 对 80.0，+5.0）。

展开后「生成的 patch（current → candidate）」显示 478 行：其中 147 行被加上红色删除样式、0 行被标成新增、331 行按上下文展示。被标红的行以 `---`（YAML front matter 分隔符）和 `- **所有模式**…`（Markdown 无序列表）开头，并非被删掉的正文。

### 数据侧对照

第 4 轮 `candidate_committed` 事件里的真实 `unifiedDiff` 是 72 行新增、0 行删除；第 3 轮到第 4 轮的目标文件从 406 行增长到 478 行。第 1 至第 4 轮全部为新增型改动，没有任何一轮发生过整文件回退或大面积删除。第 4 轮 `round.patch` 同时保存了 `intent`（3 条编辑）与 `report`（逐条应用状态），其中 `replace` / `insert_after` 的 `target` 都是「需求覆盖度关卡」相关段落，和被选中的簇直接对应。

### 关于「报错」的复核

按页面路径复核时，该 run 没有终态错误：第 4 轮处于评测中，随后第 5 轮进入评测；截至本 issue 记录时 4 轮已接纳、`error` 为 `null`、执行日志无 `run_failed`。同一对象更早的 run `01M885592456VVK5B68DSMRKTE` 确实在第 3 轮 patch 阶段失败，错误为 `claude-code edit submission failed validation`；该问题的根因（`insert_after` 的多行锚点被校验器拒绝）已由 `#599` 分析并由 `#607` 修复，与本 run 的整文件预览不是同一条链路。本次 issue 只处理「页面把整文件内容渲染成大面积删除」这一显示契约缺陷。

### 影响

该显示会让人误以为自进化候选删除了技能的大部分内容，从而误判模型质量或要求回滚一个实际只有新增的候选。由于区块展示的是完整 `SKILL.md`，而不是变更片段，评审者也无法从第 6 步看出改动与 `cluster_probe.description` 的对应关系；真正的变更只能去执行日志的 `candidate_committed` 事件里翻 `unifiedDiff`。

## 目标

- 第 6 步的 patch 区域只展示真实变更片段，不再把整文件中的 Markdown 列表、front matter 分隔符当成删除行。
- 新轮次从落库数据即可拿到真实 diff；历史轮次在没有 diff 时也必须安全降级，不产生红色「删除」误报。
- 前端和后端对 `patch.lines` / `patch.diff` 的语义有唯一契约，并由回归测试锁住。
- 保留第 6 步现有的 patch / candidate / push / eval / 接纳信息结构，不改评测与 git 行为。

## 输入依据（cluster_probe.description 与 edit patch 的关系）

**结论：不是基于 `cluster_probe.description` 直接生成的 patch。** `cluster_probe.description`（落库字段为 `probe_clusters.probe_cluster_description`）是提示词输入之一；真正的 patch 是模型在只读工作区探索后产出的 `EditPlan`，再由确定性应用器把整个目标文件覆盖成新内容。页面展示的是覆盖后的整文件，因此丢掉了「相对上一版改了什么」。

- `cluster_llm._compose_description()` 把簇描述合成为 `{type} 类问题 · {title} · {summary}`（有长度上限），`stages._cluster_title()` 只为卡片标题截取前两段，不改提示词里的完整描述。
- `advance.build_candidate_trace()` 把 `cluster.probe_cluster_description` 放进 `CandidateTrace.cluster_title`，把去重后的 `probe_analysis` 放进 `analysis`，把每条 `probe_description` 放进 `sources[].description`。
- `patch_source._edit_prompt()` 使用 `cluster_title`（≤300 字符）、`analysis`（≤1800 字符）、最多 5 条代表证据（每条 description ≤240 字符或 analysis ≤360 字符），再追加允许路径、编辑预算与「优先最小、可回退的真实修复」要求。
- `apply_edit_plan()` 在临时镜像上应用计划；`_patch_from_content()` 把应用后的文件按行拆成 `lines`，并标记 `overwrite=True`；`_stored_patch()` 落库 `files[].lines / overwrite`、`note`、`intent`、`report`。
- `git_candidate.publish()` 把真实 `candidate.unified_diff` 只写进 `candidate_committed` 事件；`stages._round_patch()` 只投影 `file / lines / overwrite`，`StepRoundPatch` 没有 diff 字段；`DiffView.vue` 再按行首 `+` / `-` / `@@` 给全文着色。

## 根因分析

### 结论

直接原因是读取契约与渲染契约对 `lines` 的语义理解相反：agent-edit 轮次落库的是整文件覆盖后的全文，前端却把它当 unified diff，一行行按首字符分类。凡是 Markdown 无序列表（`- `）和 YAML front matter 分隔符（`---`）都会命中 `startsWith("-")`，被渲染成删除；真实 diff 里的新增前缀又不存在，于是看起来只剩下「疯狂删除」。

系统性原因是第 6 步的可审计信息被截断：`intent`、`report` 和真实 `unifiedDiff` 都已经存在，却没有进入 `StepRoundPatch` 读模型；页面只能拿全文冒充 diff。测试也只用了人工构造的 `-old / +new` 行，没有用 `_stored_patch()` 的真实全文输出覆盖 Markdown 场景，因此 CI 未拦住。

### 分析过程

1. 以 admin 登录生产前端，打开上述 run 的第 6 步并展开第 4 轮；DOM 统计得到 `.dline` 478 行、`.dline.del` 147 行、`.dline.add` 0 行、`.dline.ctx` 331 行，前几条 `.del` 文本为 `---` 和 `- **所有模式**…`。
2. 读取同一 run 的 `GET /api/evolution/runs/{id}/events`；第 4 轮 `candidate_committed` 的 `unifiedDiff` 为 72 行新增、0 行删除，和页面上的 147 行删除矛盾，说明页面没有渲染这份 diff。
3. 读取 `GET /api/evolution/runs/{id}/steps/iteration`；第 4 轮 `patch.files[0]` 是 478 行、`overwrite=true`，没有 `diff` 字段；这是整文件内容，不是 diff。
4. 沿后端链路定位：`_patch_from_content()` 生成全文，`_stored_patch()` 只落库全文与 intent/report，`_round_patch()` 只投影 `file / lines / overwrite`，`DiffView.vue` 的 `lineClass()` 只做首字符判断。
5. 对照真实编辑计划：第 4 轮 `intent.edits` 的 3 条编辑分别替换/插入「建立验收矩阵」「需求覆盖度关卡」段落，说明改动与簇描述确实相关；页面之所以看起来无关，是因为它展示了 478 行全文而不是这 3 处变更。
6. 核对测试：`RunDetailConformance.test.ts` 的 DiffView 用例只传 `@@ / -old / +new / context` 人工行；API 测试只校验 patch 的形状与文件数，没有把真实 `_stored_patch()` 输出（含 Markdown 列表和 `---`）喂给读模型与渲染。

### 责任边界

- 不是模型删除了内容，也不是簇描述或归因输入错了：第 4 轮真实 diff 为 0 行删除，3 条编辑均围绕所选簇的验收门禁。
- 不是 `#522`（读取 500）回归：该 run 的 `steps/iteration` 已正常返回 200，问题发生在投影之后。
- 不是 `#599`（多行 `insert_after` 校验失败）：该缺陷只发生在 patch 生成阶段并导致 run 失败；本 run 的 edit 调用全部成功。
- 不是评测、推送或 git candidate 的问题：第 1 至第 4 轮均已推送并被接纳，run 状态正常。

## 推荐方案（唯一）

**把第 6 步的 patch 契约改成「携带并渲染真实 diff」：写侧持久化 candidate 的真实 `unifiedDiff`，读侧投影 `patch.diff`，前端只渲染 diff；历史轮次用已落库的 `intent` + `report` 合成变更块，绝不把整文件行按 `-` 着色。**

1. 写侧：`git_candidate.publish()` 在 candidate commit 之后把 `candidate.unified_diff` 一并写入 `round.patch`（复用 `PatchBundle.unified_diff` 字段），`round_patch.stored_bundle()` 能把它读回来；不重新计算 diff。
2. 读侧：`StepRoundPatch` 增加 `diff: list[str] | None`；`_round_patch()` 优先使用落库的 diff，缺失时按 `intent` 中实际应用的编辑（结合 `report` 状态）合成 `-` / `+` / hunk 行，仍缺失时返回 `null`。
3. 前端：`DiffView` 在 `patch.diff` 存在时只渲染 diff；`diff` 为 `null` 时显示中性的「候选文件内容（整文件预览）」，不再执行 `+` / `-` / `@@` 分类，也不把 Markdown 列表和 `---` 标红。
4. 契约与测试：运行 `pnpm contract:generate` 更新 `packages/contracts`；在 `apps/api/tests` 用真实 `_stored_patch()` 输出（含 478 行全文、147 个 `-` 开头行）断言读模型不再把全文当 diff；在 Web 单测覆盖 `---` 与 `- ` 行；E2E 用该 run 或等价 fixture 截图对照。
5. 部署后用本文的 run 复核：第 4 轮只显示 72 行新增、0 行删除，红色删除行归零；历史轮次也能看到与簇对应的变更块。

## 设计依据

- [05 §3.6](../../../plans/fullstack-design/05-api-design.md)：`steps/iteration` 的 `rounds[]` 契约与 patch 投影规则。
- [08 §10.3](../../../plans/fullstack-design/08-frontend-implementation.md)：第 6 步 patch / candidate / push / eval / 接纳的渲染结构。
- [07 §5.5.4](../../../plans/fullstack-design/07-backend-implementation.md)：agent-edit 的只读探索、EditPlan 应用与 intent / diff 审计。
- `.agents/flow/issues/bugfix-iteration-patch-read.md`（`#522`）与 `bugfix-agent-edit-iteration.md`（`#488`）：本轮读取模型与 agent-edit 落库结构的前置事实。

## 实现内容

- `apps/api/app/service/evolution/git_candidate.py`：candidate commit 后把 `unifiedDiff` 写入 round patch。
- `apps/api/app/service/evolution/round_patch.py`：解析落库 diff；保持旧格式兼容。
- `apps/api/app/service/evolution/stages.py`：`StepRoundPatch` 增加 `diff` 投影，并实现 intent/report 的历史轮次回退。
- `apps/web/src/pages/evolution/components/DiffView.vue`：按 diff 渲染，整文件回退时改用中性预览。
- `packages/contracts`、`apps/api/tests`、`apps/web/src/**/*.test.ts`、`tests/e2e`、`plans/fullstack-design/05-api-design.md`、`plans/fullstack-design/08-frontend-implementation.md`。

## 实施步骤

1. 写侧落库 diff，并用单测固定 `_stored_patch()` → `stored_bundle()` 的往返。
2. 读侧投影 `diff`，补 intent/report 回退与无 diff 的 `null` 分支。
3. 前端改为 diff 优先、整文件回退中性化，补 `---` 与 Markdown 列表的回归用例。
4. 更新 OpenAPI 契约、设计文档与 E2E fixture，跑聚焦门禁。
5. 部署后在 `01M8957ATHZX4K48K9PGXSVSVK` 第 4 轮复核红色删除行归零。

## 依赖与交付边界

- 依赖：`bugfix-21`（agent-edit 落库 intent / diff 的能力）与 `bugfix-27`（patch 读取模型）。
- 边界：只改第 6 步 patch 的持久化、读取、渲染与测试；不重算 git diff，不改 patch 生成、聚类、评测和推送。
- 历史轮次不做数据迁移：通过 `intent` / `report` 回退展示；没有可用数据的轮次显示整文件中性预览，不伪造 diff。

## 独立验证

```sh
TOKEN=$(curl -s -X POST http://8.149.232.63/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"<AI_EVAL_PASSWORD>"}' | jq -r .accessToken)
curl -s -H "Authorization: Bearer $TOKEN" "http://8.149.232.63/api/evolution/runs/01M8957ATHZX4K48K9PGXSVSVK/steps/iteration" | jq '.payload.rounds[] | select(.roundId == "01M895GAE675SWVN0B2789W5J5") | .patch'
```

- 预期 `diff` 存在，且包含 72 个 `+` 行、0 个真实删除行；页面第 4 轮不再出现红色 `---` 或 `- **所有模式**`。
- 运行 `pnpm test:api`、`pnpm test`、`pnpm typecheck:web`、`pnpm contract:check`、`pnpm test:e2e --pattern evolution`、`pnpm verify:flow`，全部通过。

## 验收标准

- 第 4 轮页面展示真实 diff：72 行新增、0 行删除，147 行红色误报归零。
- 新轮次的 `patch.diff` 来自落库的 `candidate.unifiedDiff`；历史轮次（如本 run）通过 `intent` / `report` 展示变更块，或降级为无着色的整文件预览。
- 测试覆盖真实 `_stored_patch()` 输出中的 `---`、`- ` 行，确保不会被判为删除；同时覆盖无 intent / 无 diff 的轮次。
- 契约、设计文档与 E2E 证据同步更新，CI 全绿。

## 门禁与 CI

- `pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api`、`pnpm test`、`pnpm typecheck:web`、`pnpm contract:check`、`pnpm test:e2e --pattern evolution`、`pnpm verify:flow`、`pnpm verify:docs`。
- 提交与 PR 标题带 `(#N)`。

## 非目标

- 不改 `cluster.review` / `cluster.score` 的聚类或描述生成，也不改 `cluster_probe.description` 的格式。
- 不改 patch 生成策略、`EDIT_BUDGET`、`MAX_CONTENT_LINES` 或 agent 工具面。
- 不改评测、推送、candidate 状态机与最终 commit message。
- 不做历史 round 的批量数据迁移，也不重写已接纳轮次的落库内容。
