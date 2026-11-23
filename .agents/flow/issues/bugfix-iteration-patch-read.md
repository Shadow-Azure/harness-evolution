# 运行详情第 6 步读取 round patch 时 500：读取契约与落库结构不一致

[English](bugfix-iteration-patch-read.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-27
milestone: bugfix
depends:
  - bugfix-21
priority: P2
status: done
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
  number: 522
  url: https://github.com/Shadow-Azure/harness-evolution/issues/522
```

## 背景

### 问题场景

2026-11-23 10:54，用户在生产 `http://8.149.232.63/`（admin）打开运行详情：

- 运行：`01M834EBAY3C9BB3TM8V85VHQN`（target `codespec-subagent-driven-development@openspec-cn-main-copy-ar-a7ec200-claude-core`，工作空间 `OpenSpec-cn_SWE-bench`）
- 路径：`/workspaces/01M7KJ05ENF9784GPBDV544VB0/evolution/runs/01M834EBAY3C9BB3TM8V85VHQN?step=iteration`
- 现象：第 6 步「迭代优化」位置出现红色错误卡，标题 `EVOLUTION_RUN_STEP_UNAVAILABLE`、副标题「加载失败」，正文「当前步骤读取失败，请重试」，底部「重试」按钮。

生产现场（第 6 步位置被替换成错误卡，本该渲染轮次卡片）：

![生产运行详情第 6 步：迭代优化返回错误卡](https://github.com/Shadow-Azure/harness-evolution/releases/download/iteration-step-500-evidence-20261123/prod-iteration-error.png)

同一次访问里其余六步都正常：运行状态「✓ 已完成 · 自进化有效」，关联 Session 7、潜在 bad case 7、归因 7、1 个簇、终评 85.0 对 80.0；执行日志 21 条完整。点「重试」仍是同一张卡片。

### 复现与观测

1. 浏览器登录 admin 打开上述路径，第 6 步错误卡稳定出现；Network 里 `GET /api/workspaces/<wid>/evolution/runs/<rid>/steps/iteration` 返回 500，连续重试 3 次全部 500：

   ```json
   {"error":{"code":"INTERNAL","message":"internal server error","details":{"requestId":"req_a07a250ab8b34b94acd080ff76d4402c"}}}
   ```

2. 同一 run 的另外六个 step 端点都是 200：`range` / `sessions` / `potential` / `attribution` / `clusters` / `final`。
3. 另一个已完成 run（`01M80MSB72NFZNDKK2Q3YN991K`，2026-11-22 11:28 创建）访问第 6 步正常返回并渲染轮次卡片。
4. 运行本身的存储事实齐全：`final` 步骤返回 1 条已接纳变更（commit `dfea5b04fba65fd270268fa1d8645b3a2b1f46a7`、簇 `01M834EBN8W2AWGT4K1JPG0VM8`），执行日志显示 candidate 已提交、推送、评测并接纳。

由此可以排除运行状态、评测、推送、前端路由与步骤状态机：是这一个 run 的持久化数据在后端读取时抛了异常。

### V2 原型对照

V2 原型第 6 步在 `plans/ui-prototype-v2/harness-evolution.html` 的 `evStepIter()` / `evCluster()`：每个聚类一轮卡片，展开后依次是「来源 bad case」表、「归因复核」、「生成的 edit patch（current → candidate）」diff、「评测对比（验证集）」与已接纳 commit 卡片。

原型第 6 步全貌（打桩数据 `EV-20261109-01`，deep-research，视口 1500×1000；与生产不是同一个 run，只对照同一步骤的信息结构与渲染结果）：

![V2 原型第 6 步：轮次卡片正常渲染](https://github.com/Shadow-Azure/harness-evolution/releases/download/iteration-step-500-evidence-20261123/proto-iteration.png)

原型轮次细节（patch diff / 评测对比 / commit 卡片）见验收截图：修复后的本地冒烟按同一原型位置逐项对照。

对照结论：原型在该位置应渲染轮次内容；生产现在连一个轮次卡片都没有，整块内容被替换成错误卡。这不是样式或信息密度偏差，而是这一步的读取链路整体失败。

### 影响

- 第 6 步是自进化唯一能核对「改了什么、评测涨了多少、最终 commit 是什么」的步骤。最新一次运行完全不可见，用户只能看第 7 步的汇总分。
- 前端把后端 500 统一映射为 `EVOLUTION_RUN_STEP_UNAVAILABLE`，除 requestId 外没有可操作线索；对确定性异常「重试」无效，现场无法自诊断。
- 只要 round 仍按当前结构落库，之后每个新 run 都会复现；不是一次性坏数据，也不是某个特定 bad case 的问题。

## 目标

- 第 6 步对当前落库结构（多文件 bundle `files[] / note / intent / report`，单文件时再附 legacy `file / lines / overwrite`）与历史结构（只有 `file / lines / note`）都返回 200，并完整展示轮次内容。
- 用回归测试固定 writer → reader 契约，避免落库结构再次升级时读取链无声漂移。

## 设计依据

- `plans/fullstack-design/05-api-design.md` §3.6（`steps/iteration` 的 `rounds[]` 结构；当前示例仍是单文件 `patch`）
- `plans/fullstack-design/08-frontend-implementation.md` §10.3（第 6 步沿用轮次卡：patch / candidate / push / eval / 接纳）
- V2 原型 `plans/ui-prototype-v2/harness-evolution.html` 的 `evStepIter()` / `evCluster()` / `evCommitBlock()`
- Agent Note `.agents/notes/proposed/feature/2026-11-22-evolution-real-ai-design.md`（真实 patch 源与审计记录）

## 根因分析

### 结论

第 6 步把数据库里的 `round.patch` 原样交给 `StepRoundPatch` 校验，而 `StepRoundPatch` 仍是旧的单文件结构，并且继承 `IdentityModel` 的 `extra="forbid"`。`round.patch` 的落库结构已经两次扩容：

- `#436`（bugfix-02）为支持暂停恢复，写入时增加 `overwrite`；
- `#488`（bugfix-21）为支持 agent 编辑，写入时增加 `files[] / intent / report`。

最新 run 的 patch 字典因此包含 `files / note / intent / report / file / lines / overwrite`。`model_validate` 抛出 4 个 `extra_forbidden`，`_iteration()` 不捕获，异常冒泡为 500 `INTERNAL`，前端再把所有非 `STEP_NOT_READY` 的错误统一映射为 `EVOLUTION_RUN_STEP_UNAVAILABLE`。

### 分析过程

1. **前端只是显示器**：`apps/web/src/pages/evolution/RunDetail.vue#L929-L934` 在 `stepError && stepErrorCode !== 'STEP_NOT_READY'` 时固定渲染 `EVOLUTION_RUN_STEP_UNAVAILABLE`；错误码来自 step 查询。第 6 步之外六步查询成功，排除路由与步骤状态机。
2. **后端第 6 步的读取链**：`apps/api/app/service/evolution/stages.py#L691` 的 `_iteration()` 先 `list_rounds()`，再对每条 round 调 `_round_item()`（`#L1031`）；`#L1058` 用 `StepRoundPatch.model_validate(patch)` 把存储字典直接校验成读模型。
3. **读模型落后于写模型**：`StepRoundPatch`（`stages.py#L244-L257`）只有 `file / lines / note`；它继承 `IdentityModel`，而 `apps/api/app/service/identity/schemas.py#L9-L13` 设置了 `extra="forbid"`。多一个键就是校验错误。
4. **写模型的当前形态**：`apps/api/app/service/evolution/git_candidate.py#L1099-L1115` 的 `_stored_patch()` 写 `files[]`（每个文件含 `file / lines / overwrite`）、`note`、`intent`、`report`；单文件时再合并 legacy 的 `file / lines / overwrite`。本 run 的 `candidate_committed` 事件显示 bundle 只有一个文件 `skills/codespec-subagent-driven-development/.harness-evolution/candidate-r1.md`，所以落库正是「legacy 单文件 + 4 个新增键」。
5. **本地复现**：把 `_stored_patch()` 的真实输出直接交给读模型：

   ```python
   StepRoundPatch.model_validate(_stored_patch(bundle))
   # 4 validation errors for StepRoundPatch
   # files / intent / report / overwrite -> Extra inputs are not permitted
   ```

   多文件 bundle 更严重：除 3 个额外键外还缺 `file`、`lines` 两个必填字段，共 5 个错误。也就是说，即使没有本 run 的 legacy 键，agent-edit 产生的多文件 patch 同样会 500。

6. **为什么只有最新一次运行坏**：`#436` 的部署在 2026-11-22 22:44 之后生效，`#488` 于 2026-11-23 10:22 部署；本 run 创建于 2026-11-23 10:40:58，是这两次部署后的第一个 run。2026-11-22 11:28 创建的 `01M80MSB…` 仍由旧代码写入，patch 只有 `file / lines / note`，所以今天仍能渲染。
7. **为什么 CI 没拦住**：现有单测只用 legacy 形态（`file / lines / note`）作为读取 fixture，没有把写入侧 `_stored_patch()` 的真实输出喂给第 6 步投影；契约测试只校验 OpenAPI 形状，不覆盖「落库 → 读取」的端到端形状。

### 责任边界

- 不是 AI 聚类降级、评测、push、git 的失败：事件日志与 terminal 结果里这些环节都成功。
- 不是「历史数据迁移」问题：旧 round 一直合法；问题是当前写入结构没有被当前读取模型接受。
- 不是单纯的前端错误码粒度问题（虽然它也放大了不可诊断性）：只改错误码不会让第 6 步显示内容。

## 推荐方案（唯一）

**让第 6 步的读取契约从「校验原始存储字典」改为「投影当前 bundle」，并同步渲染多文件 patch。**

具体：

1. **API 读模型**：把 `StepRoundPatch` 从 `{file, lines, note?}` 改成 `{files: [{file, lines, overwrite}], note?}`；`_round_item()` 不再 `model_validate(原始 patch)`，而是复用 `_stored_bundle()`（必要时提取为共享 helper）把两种历史形态规整成 bundle（单文件 legacy 变成 1 个文件的 `files`），再显式投影成 DTO。这样后续落库再加字段也不会把读路径打挂。
2. **契约与设计文档**：运行 `pnpm contract:generate` 更新 `packages/contracts`，并把 `plans/fullstack-design/05-api-design.md` §3.6 的 `patch` 示例改成 `files[]`（保留单文件示例说明 legacy 兼容）。
3. **前端渲染**：`StepIterations.vue#L215-L221` 把 `round.patch` 传给 `DiffView`；`DiffView.vue` 按 `files` 逐个渲染，每个文件显示路径标题（与原型「生成的 edit patch」区块一致）。单文件时视觉与现在相同。
4. **回归测试**：新增 API 测试，用 `_stored_patch()` 构造 1 文件与 2 文件 round，断言 `steps/iteration` 返回 200、`patch.files` 数量与内容正确；再保留一条 legacy `{file, lines, note}` 用例。E2E 增加 bundle 形状的 run fixture，断言第 6 步渲染多个文件路径与 patch 内容；评测对比与 commit 卡片由现有第 6 步用例覆盖。
5. **Agent Note**：在 `.agents/notes/implemented/bug-fix/` 记录「读模型必须从落库 bundle 投影，禁止用 forbid-extra 模型直接校验存储字典」。

不建议的两种替代：只用 `try/except` 把异常吞成 `patch: null`，或给 `StepRoundPatch` 开 `extra="ignore"`。前者让轮次卡片失去 patch 预览（而 patch 正是第 6 步的核心信息）；后者在真实多文件 bundle 上仍缺 `file / lines`。两者都只是把 500 换成「静默缺内容」，没有对齐根因。

## 实现内容

- `apps/api/app/service/evolution/stages.py`：`StepRoundPatch` 改为 bundle 投影；`_round_item()` 复用 `_stored_bundle()`。
- `packages/contracts`：重新生成 OpenAPI 类型。
- `apps/web/src/pages/evolution/components/DiffView.vue`：多文件渲染；`StepIterations.vue` 保持原样透传 `round.patch`。
- `apps/api/tests/evolution/`、`tests/e2e/`：writer → reader 回归。
- `plans/fullstack-design/05-api-design.md`、Agent Note。

## 实施步骤

1. 改 DTO 与 `_round_item()` 投影，先让两种形态的投影单测通过。
2. 用 `_stored_patch()` 的真实输出补 API 回归测试，确认旧实现失败、新实现通过。
3. 更新前端与契约，生成 `api.d.ts`。
4. 补 E2E 场景与设计文档，跑门禁。
5. 在本 issue 回贴生产修复后的第 6 步截图与旧 run 对照。

## 依赖与交付边界

- 依赖：`bugfix-02`（`#436` 引入 `overwrite` 落库）、`bugfix-21`（`#488` 引入 `files / intent / report` 落库）。
- 边界：只改读取投影、契约、渲染与测试；不迁移历史数据，不改 patch 生成 / 评测 / 推送逻辑，不动运行终评。
- 生产修复需要一次部署；部署后复核本 run 与至少一个历史 run。

## 独立验证

复现（只读，需 admin）：

```sh
TOKEN=$(curl -s -X POST http://8.149.232.63/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<AI_EVAL_PASSWORD>"}' | jq -r .accessToken)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://8.149.232.63/api/workspaces/01M7KJ05ENF9784GPBDV544VB0/evolution/runs/01M834EBAY3C9BB3TM8V85VHQN/steps/iteration" \
  -w '\nHTTP %{http_code}\n'
```

- 现状：`HTTP 500`，`{"error":{"code":"INTERNAL",...}}`。
- 修复后：`HTTP 200`，`payload.rounds[0].patch.files` 至少 1 项，URL / 标题 / 评测 / commit 与 `final` 步骤一致。
- 回归：`01M80MSB72NFZNDKK2Q3YN991K` 第 6 步仍 200 且 patch 仍可渲染。

本地：

```sh
pnpm test:api -- tests/evolution/test_iteration_round_patch.py
pnpm test:e2e -- --pattern iteration
pnpm contract:check
pnpm verify:flow
```

- 预期：新增用例覆盖 bundle 单文件、bundle 多文件、legacy 单文件三种形状；contract 无 diff；flow 通过。

## 验收标准

- [ ] 生产同一 run 第 6 步显示轮次卡片：来源 bad case、生成的 patch（含文件路径）、评测对比、已接纳 commit，无 `EVOLUTION_RUN_STEP_UNAVAILABLE`。
- [ ] 历史 run（例如 `01M80MSB72NFZNDKK2Q3YN991K`）第 6 步行为与截图不变。
- [ ] 新增 API 回归用例在修复前失败、修复后通过，且直接使用 `_stored_patch()` 的输出作为输入。
- [ ] 多文件 bundle 在第 6 步渲染出每个文件的 diff 块，契约与设计文档 §3.6 同步。
- [ ] 第 6 步读取路径不再对存储字典做 forbid-extra 校验。

## 门禁与 CI

- `pnpm verify:flow`、`pnpm test:gates`、`pnpm contract:check`
- `pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api`
- `pnpm lint:web`、`pnpm typecheck:web`、`pnpm test:web`、`pnpm test:e2e -- --pattern iteration`
- CI 必须执行测试，覆盖率不得低于 80%。

## 非目标

- 不修复运行本身：该 run 已成功完成，终评有效。
- 不迁移或重写历史 round 数据。
- 不改 patch 生成、agent 编辑、评测与推送逻辑。
- 不统一前端错误码（例如区分 `INTERNAL` 与 `STEP_NOT_READY` 的展示）——可以另开 issue。
- 不清理本次证据 release。
