# PR #621 检视：第 6 步按真实 diff 渲染 patch

- 检视对象：[PR #621](https://github.com/Shadow-Azure/harness-evolution/pull/621)
- owning Note：[`.agents/notes/implemented/bug-fix/2026-11-23-iteration-patch-projection.md`](../.agents/notes/implemented/bug-fix/2026-11-23-iteration-patch-projection.md)
- 流程 issue：[`.agents/flow/issues/bugfix-62-iteration-patch-diff.md`](../.agents/flow/issues/bugfix-62-iteration-patch-diff.md)（[#617](https://github.com/Shadow-Azure/harness-evolution/issues/617)）
- 实现计划：[05 §3.6](fullstack-design/05-api-design.md)、[08 §10.3](fullstack-design/08-frontend-implementation.md)、[07 §5.5.4](fullstack-design/07-backend-implementation.md)
- 检视日期：2026-11-25

## §0 变更文件树与职责

共 21 个文件（A 6 / M 15 / D 0）：

```text
apps/api/app/service/evolution/
  git_candidate.py            M  提交后把真实 diff 回写 round.patch
  round_patch.py              M  stored_bundle 读回 diff
  stages.py                   M  StepRoundPatch.diff + 预算合成 + 回退
  patch_source.py             M  PatchBundle.unified_diff 语义注释
apps/api/tests/
  evolution/test_iteration_round_patch.py          M  读模型回归
  m5-11-evolution-recovery/test_full_placeholder_loop.py  M 写侧落库断言
packages/contracts/
  openapi.json                M  StepRoundPatch 新增 diff
  src/generated/api.d.ts      M  生成类型
apps/web/src/pages/evolution/components/
  DiffView.vue                M  diff 优先 + 中性整文件预览
  RunDetailConformance.test.ts M  真实 diff / 历史轮次用例
tests/e2e/
  m10-06-run-detail-v2.test.mjs        M  第 6 步断言
  support/m10_06_run_detail_fixture.py M  轮次携带真实 diff
plans/fullstack-design/
  05-api-design.md            M  patch 契约
  07-backend-implementation.md M  写侧落库 diff
  08-frontend-implementation.md M  渲染规则
.agents/flow/issues/
  bugfix-62-iteration-patch-diff.md     A  流程 issue（中文）
  bugfix-62-iteration-patch-diff.en.md  A  英文配对
  bugfix-62-iteration-patch-diff.i18n.yaml A 配对 hash
.agents/notes/implemented/bug-fix/
  2026-11-23-iteration-patch-projection.md/.en.md/.i18n.yaml M 更新 owning Note
```

## §1 一页速览

**一句话**：把第 6 步 patch 区从「拿整本病历当体检报告」改成「只打印本次改动页」：写侧存下 candidate 的真实 git diff，读侧优先投影它，历史轮次用编辑意图合成变更块，前端不再按整文件行首字符猜增减。

| 交付块 | 内容 |
|---|---|
| 写侧 | `publish()` 在 commit 后把 `CandidateWorkspace.unified_diff` 写入 `round.patch.diff`（`git_candidate.py:294`） |
| 读侧 | `stored_bundle()` 读回字符串；`_patch_diff()` 优先拆行，否则 `_intent_diff()` 合成（`stages.py:1153`、`:1166`） |
| 前端 | `DiffView` 按 `diff --git` 切块；`@@` hunk、内容行着色、文件头跳过；无 diff 时中性预览（`DiffView.vue:49`、`:83`） |
| 契约 | `StepRoundPatch.diff: list[str] \| null`，OpenAPI 与 TS 类型重新生成 |
| 证据 | E2E fixture 的 v2-round-1 带真实 diff；v2-round-2 走历史预览；冒烟截图在 PR 描述 |

验证基线（本地）：

| 命令 | 结果 |
|---|---|
| `pnpm test:api` | 2443 passed, 27 skipped |
| `pnpm test:web` | 835 passed, 1 skipped |
| `pnpm lint:api` / `pnpm typecheck:api` | 通过 |
| `pnpm lint:web` / `pnpm typecheck:web` | 通过 |
| `pnpm contract:check` | 通过 |
| `pnpm test:e2e --pattern m10-06` | 6/6 通过 |
| `pnpm test:gates` | 50 passed |
| `pnpm lint:docs` / `pnpm verify:docs` | 通过 |
| `pnpm verify:flow` / `verify:flow --diff origin/main` | 通过 |
| `pnpm verify:web-style` | 通过 |

## §2 架构导览

### 2.1 写侧：diff 只在 commit 之后存在

`PatchBundle` 在生成 patch 时构造，此时还没有 git commit，所以 `unified_diff` 为空；`publish()` 先落一次 patch（`git_candidate.py:258`），commit 成功后再用 `_with_candidate_diff()` 把它并入持久化字典（`git_candidate.py:294`）。这样保持「patch 字节先落、diff 后补」的顺序，不重算 diff，也不改动 candidate 的 hash / trailer 语义。

### 2.2 读侧：唯一还原缝

所有读者继续走 `stored_bundle()`（`round_patch.py:22`）。新增的 `diff` 是字符串，`StepRoundPatch.diff` 是行数组，转换只发生在 `_patch_diff()` 一处；`intent` / `report` 的合成只使用 `status == "applied"` 的编辑，跳过编辑不会进入展示。历史轮次没有 diff 时，`_intent_diff()` 生成 `diff --git` + `---` / `+++` + `@@ 编辑 N` + `-` / `+` 变更块；没有 intent 或无 applied 编辑时返回 `null`。

### 2.3 前端：先识别文件头，再给内容行着色

`DiffView` 的 `diffFiles` 以 `diff --git` 切文件块（`DiffView.vue:49`）。关键顺序是：`diff --git` → 新块；文件首个 hunk 之前的 `--- ` / `+++ ` 视为文件头丢弃；`index` / mode / rename / binary 元数据丢弃；`@@` 置 hunk 并原样展示；其余行才用 `rowKind()` 按首字符分类（`DiffView.vue:83`）。`hunkSeen` 保证 hunk 内以 `---` 开头的真实删除行不会被误认为文件头。

### 2.4 契约

`StepRoundPatch` 新增可选 `diff`；`IdentityModel` 仍 `extra="forbid"`，读侧继续先还原再投影。`packages/contracts` 由 `pnpm contract:generate` 生成，禁止手改。

## §3 数据流走查

1. `AgentEditPatchSource.build_bundle()` 产出整文件 `files[]`、`intent`、`report`，`unified_diff` 仍为空。
2. `EvolutionCandidateService.publish()` 落 patch（无 diff），创建 candidate commit。
3. `create_candidate_bundle()` 返回 `CandidateWorkspace.unified_diff`（git 真值）。
4. `_with_candidate_diff()` 把 diff 并入 `saved`，`mark_round_candidate()` 持久化。
5. `GET /steps/iteration` → `_round_item()` → `_round_patch()` → `stored_bundle()` 还原字符串 diff。
6. `_patch_diff()` 优先 `splitlines()`；历史轮次走 `_intent_diff()`；都没有则 `null`。
7. 前端有 `diff` 时渲染文件块 + 内容行；`null` 时渲染 `files[]` 中性预览。

## §4 导读地图

| 文件 | 状态 |
|---|---|
| `apps/api/app/service/evolution/git_candidate.py` | ✅ |
| `apps/api/app/service/evolution/round_patch.py` | ✅ |
| `apps/api/app/service/evolution/stages.py` | ✅ |
| `apps/api/app/service/evolution/patch_source.py` | ✅ |
| `apps/api/tests/evolution/test_iteration_round_patch.py` | ✅ |
| `apps/api/tests/m5-11-evolution-recovery/test_full_placeholder_loop.py` | ✅ |
| `apps/web/src/pages/evolution/components/DiffView.vue` | ✅ |
| `apps/web/src/pages/evolution/components/RunDetailConformance.test.ts` | ✅ |
| `tests/e2e/m10-06-run-detail-v2.test.mjs` | ✅ |
| `tests/e2e/support/m10_06_run_detail_fixture.py` | ✅ |
| `packages/contracts/openapi.json` / `api.d.ts` | ✅（生成物） |
| `plans/fullstack-design/05/07/08` | ✅ |
| `.agents/**` 三件套 | ✅ |

## §5 人工验收清单

- [ ] 打开第 6 步，确认新轮次 patch 区显示真实 diff；文件头行不出现红色删除。
- [ ] 历史轮次（无 diff）显示「整文件预览，不对行着色」，无红色删除。
- [ ] 带多文件 diff 的轮次每文件一个标题，新增/删除计数只统计内容行。
- [ ] 对照 V2 原型第 6 步，确认文件标题、hunk、context、增删配色一致。
- [ ] 部署后在 `01M8957ATHZX4K48K9PGXSVSVK` 第 4 轮复核红色删除行归零。

## §6 讨论点

### D1 落库 diff 不截断

- **位置**：`apps/api/app/service/evolution/git_candidate.py:1094`
- **现象**：`_with_candidate_diff()` 原样保存 `candidate.unified_diff`；事件载荷仍按 20k 字符截断，但 `round.patch.diff` 不截断。
- **问题**：整文件覆盖型轮次的 diff 可能达到数十 KB，`evolution_rounds.patch` JSON 会变大一倍左右；极端编辑计划（8 × 400 行）会更大。
- **预判**：为保住「页面与 `candidate_committed` 一致」的审计面，不截断是合理的；目前单轮最大 diff 远小于数据库字段上限，且 patch 本来就是整文件，增加量同阶。
- **结论**：（留空给维护者）

### D2 历史轮次合成 diff 没有行号

- **位置**：`apps/api/app/service/evolution/stages.py:1166`
- **现象**：`_intent_diff()` 用 `@@ 编辑 N · op @@` 作为 hunk 头，`insert_after` 把锚文本作为 context，但没有真实行号。
- **问题**：读者可以知道「改了什么」，但不能像 git hunk 一样跳转到文件行；如果后续要做「在文件中定位」，需要额外保存上一版内容或行号。
- **预判**：本 issue 的目标是消除误报并保留可审计的变更块，不是还原历史 diff；当前信息量（编辑序号、op、target/content、applied 状态）足以对应簇描述。
- **结论**：（留空给维护者）

### D3 文件头识别依赖 `diff --git`

- **位置**：`apps/web/src/pages/evolution/components/DiffView.vue:49`
- **现象**：只有 `diff --git a/... b/...` 会开启新文件块；若上游 diff 使用其它前缀（如 `diff --cc`），文件头会被当作 context。
- **问题**：candidate diff 由 `git diff`（非 merge）产生，当前只会是 `diff --git`；未来若 candidate 从 merge commit 生成，需要扩展前缀。
- **预判**：当前无实害；把识别收敛在 `DIFF_GIT_HEADER` 一处，后续扩展成本低。
- **结论**：（留空给维护者）

### D4 历史 fixture 的 `diff` 必须是字符串

- **位置**：`tests/e2e/support/m10_06_run_detail_fixture.py:778`
- **现象**：fixture 最初把 diff 写成行数组，API 返回 `diff: null`，E2E 才发现；现在改为 `"\n".join([...])`。
- **问题**：落库契约是字符串（与 `CandidateWorkspace.unified_diff` 一致），读侧只接受字符串；fixture 与真实写侧形状必须一致，否则测试会静默走回退分支。
- **预判**：已在 E2E 断言新轮次 `added=2 / deleted=1`，fixture 走错形状会立即失败；读侧不需要为测试便利放宽类型。
- **结论**：已决（2026-11-25）：保持字符串契约，修 fixture。

## §7 分流表

| 发现 | 定性 | 去处 | 状态 |
|---|---|---|---|
| 整文件内容被当 diff 着色 | bug | 本 PR 修复 | ✅ |
| 历史轮次无 diff 时红删误报 | bug | 本 PR 修复 | ✅ |
| CI `flow-online` 报「PR 未关联 milestone」 | process | 本检视文档 + PR 设置 | ✅ 已 `gh pr edit --milestone` |
| diff 落库体积 | decision | D1 待维护者 | 讨论中 |
| 历史合成 diff 无行号 | decision | D2 待维护者 | 讨论中 |

## §8 链接

- PR：https://github.com/Shadow-Azure/harness-evolution/pull/621
- Issue：https://github.com/Shadow-Azure/harness-evolution/issues/617
- 冒烟证据：https://github.com/Shadow-Azure/harness-evolution/releases/tag/issue-617-evidence-20261125
- owning Note：`.agents/notes/implemented/bug-fix/2026-11-23-iteration-patch-projection.md`

## §9 文件级代码分析

### `git_candidate.py`

职责：候选 patch 的持久化与提交后状态推进。变更只有两处：提交成功后合并 diff（`:294`），以及 `_stored_patch()` 能序列化 `PatchBundle.unified_diff`（`:1070`）。`_with_candidate_diff()` 是纯函数，空 diff 原样返回，避免覆盖已有值；不触碰 hash、trailer、重试路径。

### `round_patch.py`

职责：写读共享的还原缝。新增 `diff = raw.get("diff")` 与 `unified_diff=` 参数；非字符串（例如早期 fixture 的数组）被忽略，行为退化为中性预览。没有新增闭包模型，保持 `extra="forbid"` 边界。

### `stages.py`

职责：七步读模型投影。`StepRoundPatch` 新增可选 `diff`；`_round_patch()` 追加 `diff=_patch_diff(bundle)`；`_patch_diff()` 与 `_intent_diff()` 是纯函数，不查库、不抛异常。合成时只取 `report.status == "applied"`，按 `intent.edits` 原顺序输出。

### `DiffView.vue`

职责：第 6 步 patch 展示。由「所有行按首字符着色」改为「解析文件块 + 元数据过滤 + 内容行着色」。`hasDiff` 决定模板分支；预览分支保留原 `files[]` 路径标题，但应用 `.preview` 中性样式并显示说明文案。

### 测试与文档

API 回归同时覆盖写侧 `_stored_patch()` 与读侧 `_round_patch()`；Web 用例分别覆盖真实 diff、`---` 内容行、历史预览；E2E 覆盖两文件 diff 与历史轮次 0 红删。设计文档 05/07/08 与 owning Note 同步，双语配对已重录。
