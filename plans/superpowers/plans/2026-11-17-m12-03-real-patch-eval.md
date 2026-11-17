# Real Patch Generation and Evaluation Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder-only patch/eval loop with an extensible real implementation: a pluggable patch source (placeholder + minimal-config-change side by side), a mode-driven evaluation gateway factory (fake default, HTTP skeleton opt-in), and one durable end-to-end evidence loop backed by real local git operations.

**Architecture:** `advance` 阶段通过新增 `PatchSource` 接缝生成真实落盘 patch（工厂 + Protocol + 子类，按 run 的 `eval_config["patchMode"]` 与全局 `HE_PATCH_SOURCE_MODE` 选择）；评测接入升级为 mode 驱动的 `EvalGateway` 工厂（`eval_config["mode"]` + `HE_EVAL_*` env 兜底），新增 `HttpEvalGateway` + `EvalMapper`（baseUrl/apiKeyRef 间接引用，未配置 baseUrl 显式报错，默认仍 fake）；闭环证据用真实 bare remote + 真实 git push/accept/reject/finalize 在测试中固化。

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy async, pytest/pytest-asyncio, httpx, subprocess git（真实操作，非 mock）。

**Spec:** [plans/fullstack-design/07-backend-implementation.md §5.6–5.8.1](../../../plans/fullstack-design/07-backend-implementation.md), [plans/fullstack-design/01-architecture.md §4.3](../../../plans/fullstack-design/01-architecture.md), [plans/fullstack-design/09-review-guide.md R11](../../../plans/fullstack-design/09-review-guide.md), `.agents/flow/issues/m12-03-real-patch-eval.md`

## Global Constraints

- 前端零改动、UI 类型不变；不改 `packages/contracts` 契约形状（`POST /runs` body 的 `eval` 字段已存在，无需 contract:generate）。
- 默认行为向后兼容：未配置时仍走占位 patch source 与 fake gateway；显式未知 mode 必须报配置错误，不静默降级。
- 密钥不落仓库、不落库：`apiKeyRef` 只存环境变量名，密钥从 env 间接解析；测试用假密钥与本地文件。
- candidate ref 命名 `evo/{YYYYMMDD}-{run_id}/candidate/r{seq}`；push 3 次 / 5s 重试；accept amend → force-with-lease → ff run 分支；拒绝删 ref 不 reset；blocked 语义按 §5.6/§5.8.1。
- 闭环测试必须真实 git 操作 + 真实落盘（bare remote + 工作区 commit + `git ls-remote` 断言），不 mock git。
- 新增代码测试覆盖 ≥80%；测试放 `apps/api/tests/m12-03-real-patch-eval/`。
- `reports/` 与 `.env` 不入库；证据文件 `reports/2026-11-17-m12-03-evidence.md` 只留本地。
- commit 标题含 `(#244)`；不 push、不建 PR、不合并。
- 常驻文档中英成对；同一 PR 至少一条 Agent Note。

## Review Focus

- 占位 patch 被误当真实结论的风险（09 R11）：minimal-config patch source 必须让 commit message 的「改动」段描述真实配置变更，占位 source 保持 V1 标注。
- gateway 选择必须由 run 创建期快照 + env 兜底决定；`mode: "http"` 但缺 `baseUrl` 时必须显式失败而不是退回 fake。
- `Patch` 语义扩展（overwrite）不得破坏既有追加式占位 patch 与 m5-09/m5-10 行为。
- HttpEvalGateway 的错误必须进入 `blocked(stage=eval)` 既有路径，不新增 event_type。
- deploy secrets 注入必须在 secrets 未配置时跳过，不阻塞现有部署；workflow 不回显密钥。

### Task 1: PatchSource seam (placeholder + minimal-config, real files)

**Files:**
- Create: `apps/api/tests/m12-03-real-patch-eval/test_patch_sources.py`
- Modify: `apps/api/app/service/evolution/git_candidate.py`（`PatchSource` Protocol、`PlaceholderPatchSource`、`MinimalConfigPatchSource`、`default_patch_source_factory`、publish 接线、trace `patch_note`）
- Modify: `apps/api/app/third_party_api/git/workspace.py`（`Patch.overwrite` 语义）

- [x] Write failing tests: placeholder source reproduces the current `.harness-evolution/candidate-r{n}.md` patch; minimal-config source merges one deterministic config key derived from the bad-case text into `{sub_dir}/config/{target_name}.json`, rejects unknown modes, and never allows path traversal.
- [x] Write failing tests: `Patch.overwrite=True` replaces file content in a real workspace while default append behavior stays unchanged.
- [x] Implement the seam and factory (`eval_config["patchMode"]` override + `HE_PATCH_SOURCE_MODE` fallback), wire `publish` to build patches through it, and let the「改动」message section describe the real change.
- [x] Run focused tests until green; re-run m5-09/m5-10 suites for no regression.

### Task 2: Mode-driven eval gateway factory + HttpEvalGateway skeleton

**Files:**
- Create: `apps/api/tests/m12-03-real-patch-eval/test_gateway_factory.py`
- Create: `apps/api/tests/m12-03-real-patch-eval/test_http_eval_gateway.py`
- Create: `apps/api/app/third_party_api/eval_gateway/__init__.py`, `mapper.py`, `http.py`
- Modify: `apps/api/app/service/evolution/engine/contracts.py`（`EvalGatewayConfigError`、mode-driven `default_gateway_factory` 签名保持兼容）
- Modify: `apps/api/app/config.py`（`HE_EVAL_MODE` / `HE_EVAL_BASE_URL` / `HE_EVAL_API_KEY`、`HE_PATCH_SOURCE_MODE`）

- [x] Write failing tests: factory resolves `fake` by default, `http` from run snapshot or env fallback; `http` without baseUrl raises an explicit config error; apiKeyRef is an env-var name resolved indirectly, missing env → config error; unknown mode → config error.
- [x] Write failing tests: `EvalMapper` round-trips submit/status/result JSON; `HttpEvalGateway` performs real HTTP calls against a local stub server (submit → queued → completed → result) and maps HTTP failures into gateway errors.
- [x] Implement `HttpEvalGateway` per §5.7 (`submit/get_status/get_result`, internal stable models unchanged) and the mode-driven factory.
- [x] Run focused tests until green.

### Task 3: Composition wiring with unchanged defaults

**Files:**
- Modify: `apps/api/app/main.py`（inject gateway factory + patch source factory from settings）
- Create: `apps/api/tests/m12-03-real-patch-eval/test_app_wiring.py`

- [x] Write a failing test proving `create_app` wires the mode-driven factory while an unconfigured environment still resolves `FakeEvalGateway` and the placeholder patch source.
- [x] Implement wiring; confirm the OpenAPI surface is unchanged (`pnpm contract:check`).

### Task 4: Real closed-loop evidence (real git, real eval, real decision)

**Files:**
- Create: `apps/api/tests/m12-03-real-patch-eval/test_real_loop_evidence.py`
- Create (local only, gitignored): `reports/2026-11-17-m12-03-evidence.md`

- [x] Write the closed-loop test: real bare remote + seed repo with a config file; prepare → advance (minimal-config patch, real commit, real push to `refs/tags/{candidate_ref}`) → eval via opt-in HttpEvalGateway against a local eval stub → accept (amend → force-with-lease → ff → push run branch → delete candidate ref) → finalize; assert run/cluster/probe/bad_case traceability and remote ref states with `git ls-remote`.
- [x] Add the mirrored reject-path assertions: rejected candidate ref deleted, run branch unchanged.
- [x] Support `HE_M12_03_EVIDENCE_OUT` to dump the traceable evidence summary; run once to produce `reports/2026-11-17-m12-03-evidence.md` (not committed).

### Task 5: Production env injection via GitHub Secrets + docs + scope

**Files:**
- Modify: `deploy/env.production.example`（HE_EVAL_* 段）
- Modify: `.github/workflows/deploy.yml`（可选 secrets → `/opt/harness/shared/.env` 注入，未配置跳过）
- Modify: `docs/deployment.md` + `docs/deployment.en.md`（「评测配置注入」节，成对）
- Modify: `plans/deploy-aliyun-playbook.md`（操作步骤）
- Modify: `.agents/flow/issues/m12-03-real-patch-eval.md` + `.en.md`（scope 增加 `deploy/**`、`.github/workflows/**`，正文说明理由）

- [x] Extend the issue scope on both language sides with one sentence explaining the user-mandated secrets injection.
- [x] Add the HE_EVAL_* env example block and the optional deploy.yml injection step (skip when secrets absent, no echo of values).
- [x] Add the paired docs section and playbook steps.

### Task 6: Agent Note (bilingual pair)

**Files:**
- Create: `.agents/notes/implemented/architecture/2026-11-17-real-patch-eval-seams.md` + `.en.md` + `.i18n.yaml`

- [x] Write the note (Problem/Decision/Alternatives/Consequences) covering both seams and the secrets boundary; run `pnpm record:i18n -- <pair>`.

### Task 7: Gates, design-conformance self-check, commit

**Files:**
- Modify: only files inside the issue scope union.

- [ ] Run: `pnpm test:api -- tests/m12-03-real-patch-eval`, `pnpm test:db`, `pnpm contract:check`, `pnpm lint:api`, `pnpm typecheck:api`, `pnpm verify:flow --diff main`, plus the existing evolution test directories.
- [ ] Walk through §5.6–5.8/§5.8.1 and §4.3 conformance item by item; fix code (not design) where they disagree.
- [ ] Commit locally with `(#244)` in the subject; no push, no PR.
