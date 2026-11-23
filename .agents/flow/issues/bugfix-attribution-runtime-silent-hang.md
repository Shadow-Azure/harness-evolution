# 生产归因绑定静默挂起：补齐运行时前置校验与可见状态

[English](bugfix-attribution-runtime-silent-hang.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-32
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - apps/api/app/main.py
  - apps/api/app/service/evolution/local_attribution.py
  - apps/api/tests/**
  - apps/web/src/pages/evolution/targets/**
  - apps/web/src/pages/overview/components/TargetsOverview.vue
  - deploy/**
  - .github/workflows/deploy.yml
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - .env.example
  - plans/**
  - .agents/**
adr: []
github:
  number: 544
  url: https://github.com/Shadow-Azure/harness-evolution/issues/544
```

## 背景

2026-11-23 17:13:08 CST，生产前端把系统默认 `attribute-badcases` 绑定到进化对象 `codespec-subagent-driven-development`（target `01M7Y37ZR7N61GVWMZ31FPN8JY`，workspace `01M7KJ05ENF9784GPBDV544VB0`）。PUT 返回 200，目标行的 `attribution_package_id=default-attribute-badcases`、`attribution_generation=01M83TWE7ZSTC6Z5MNF0P0KQDM`、`attribution_due=attribution_cutoff=2026-11-23 17:13:08`。到 17:39（DB `NOW()` 17:39:51）仍是 `attribution_owner=NULL`、`attribution_failures=0`、`attribution_error=NULL`、`updated_at=17:13:08`；没有 claim，也没有失败重试。服务在 17:36 重新发布到 `065a96ae` 后状态完全不变。

### 问题描述

绑定请求成功、目标行也已写入 `attribution_due`，但后台没有任何消费者领取。25 分钟后仍无 owner、无失败、无报告、无重试；目标页只显示“已绑定”，用户无法从列表或详情判断归因是否在运行。生产机没有 `HE_ATTRIBUTION_AGENT`，也没有 bubblewrap，因此即使只补开关，批次也会在 claim 后失败并消耗绑定。该对象实际有 22 条待处理 Badcase，不是数据为空。

### 根因定位过程

1. **确认绑定与排队状态**：17:13:08 PUT 返回 200；DB 中 package、generation、due、cutoff 均已写入；到 17:39 仍是 `owner=NULL`、`failures=0`、`error=NULL`、`updated_at=17:13:08`，说明不是 worker 执行失败，而是从未被 claim。
2. **确认消费者是否启动**：`apps/api/app/main.py` 的 lifespan 只在 `resolved_settings.attribution_agent` 非空时调用 `binding_worker.start()`；`/opt/harness/shared/.env` 与 `harness-api` 进程环境都没有 `HE_ATTRIBUTION_AGENT`，release 目录没有本地 `.env`；`config.py` 默认 `None`，`.env.example` 明确“留空关闭本地归因”。
3. **确认是否有实际产出**：`attribute/<workspace>/` 下只有 `attribute_source` / `attribute_skill`，没有 `attribute_input` / `attribute_output`，也没有 generation `01M83TWE...` 的批次目录；journal 没有该 worker 的日志。
4. **确认数据面是否为空**：22 个 session 含 `codespec-subagent-driven-development` 的 skill 事件，各有 1 条 `discovery` Badcase（共 22 条，均早于 cutoff）；关联数据存在，修复后不需要重新绑定。
5. **确认运行时前置**：服务器 `dpkg` 无 bubblewrap、`bwrap` 不在 PATH、服务账号 `shutil.which("bwrap")` 为 `None`；`apps/api/app/third_party_api/ai_agent/claude_skill.py` 在 Linux 缺 bwrap 会抛 `attribution requires bubblewrap on Linux`。只加 `HE_ATTRIBUTION_AGENT=provider` 会让批次 claim 后失败，3 次后 `attribution_due=NULL`，绑定被消耗。
6. **确认 UI 可见性**：目标页只有编辑弹窗里的一句提示，列表/详情没有持续状态；服务在 17:36 重新发布到 `065a96ae` 后 due/owner 状态完全不变，说明不是一次性请求失败。

### 结论

- 直接原因：生产未启用归因运行时（`HE_ATTRIBUTION_AGENT` 缺失），`BindingWorker` 从未启动；绑定任务一直停在队列。
- 第二阻塞：服务器缺 bubblewrap；即使只补开关，第一批也会失败并消耗重试。
- 放大因素：UI 只在编辑弹窗提示，绑定后没有持续状态；用户看到“已绑定”会误以为已开始。
- 非根因：绑定写入、generation/due 生成、对象匹配与 22 条 Badcase 数据都正常；不是绑定 API 或数据面缺陷。
- 修复方向：复用现有 AI Agent 配置补上归因开关（`HE_ATTRIBUTION_AGENT=provider`），加运行时/发布前置校验和可见状态；生产安装 bubblewrap 后，现有 generation 自动处理。

## 目标

- 复用现有 AI Agent 配置：不新增第二套 provider/model/API key，Deploy 在 `AI_AGENT_PROVIDER` 非空时注入 `HE_ATTRIBUTION_AGENT=provider`，复用同一 CLI、共享 settings 和 `ANTHROPIC_API_KEY`。
- 运行时不可用时可见：目标配置页与对象总览在 `runtimeEnabled=false` 时持续显示原因，已绑定行显示“归因未运行”。
- 前置缺失时快速失败：启动日志给出稳定错误码并跳过 worker，不 claim、不消耗排队绑定；发布前置检查在切换 `current` 前失败。
- 生产恢复：安装 bubblewrap 后，现有 generation `01M83TWE...` 自动处理约 22 条 Badcase；文档给出启用与验证步骤。

## 设计依据

- [归因 Agent 执行器 Note](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-17-attribution-agent-executor.md)：本地 Skill 执行使用逐次文件系统沙箱（Linux bubblewrap），`HE_ATTRIBUTION_AGENT` 是显式开关。
- [07 §5.5.1 AI Agent Provider 出站适配层](../../../plans/fullstack-design/07-backend-implementation.md)：Provider 能力面与 Skill 支持边界。
- [07 §5.13 归因生成与缓存](../../../plans/fullstack-design/07-backend-implementation.md)：绑定批次、generation、report 写入与重试语义。
- [05 §4.1 基础端点：健康检查与鉴权](../../../plans/fullstack-design/05-api-design.md)：健康检查是发布探活入口，错误应可诊断。
- [docs/deployment.md](https://github.com/Shadow-Azure/harness-evolution/blob/main/docs/deployment.md) 与 [`HE_ATTRIBUTION_AGENT` 示例](https://github.com/Shadow-Azure/harness-evolution/blob/main/.env.example)：部署注入、配置开关与 bubblewrap 前置说明。
- `.github/workflows/deploy.yml`：现有 AI Agent 注入（`AI_AGENT_PROVIDER`、`HE_AI_AGENT_CLAUDE_BIN`、`HE_AI_AGENT_CLAUDE_SETTINGS`、`CLAUDE_CONFIG_DIR`、`ANTHROPIC_API_KEY`）与缺失即 unset 的模式；归因开关可复用同一通道。
- `apps/api/app/main.py`、`apps/api/app/config.py`、`apps/api/app/service/evolution/local_attribution.py`、`apps/api/app/third_party_api/ai_agent/claude_skill.py`：worker 门控、`provider` 选择器与 bwrap 检查的现状。

## 实现内容

根因修复方案分三层：复用现有 AI Agent 配置补上开关、运行时/发布前置校验、可见状态与文档。

- **复用现有 AI Agent 配置（推荐）**：`HE_ATTRIBUTION_AGENT=provider` 已支持复用共享 `AIAgentProvider`；Deploy 在 `AI_AGENT_PROVIDER` 非空时注入 `HE_ATTRIBUTION_AGENT=provider`，为空时 `--unset`，不新增 Secret、模型或 API key。若团队希望显式覆盖，可加同名 Variable/Secret；默认不在 `Settings` 里硬编码开启。这样生产已有 `AI_AGENT_PROVIDER=claude-code` 的部署会自动获得归因开关，同时保留显式关闭能力。
- **启动前置检查**：在 `main.py` 计算 `attribution_ready = attribution_enabled and preflight_ok`；`preflight_ok` 在 Linux 上检查 `shutil.which("bwrap")`，并复用 `local_attribution.configured_skill_provider()` 的 Skill 支持检查。把 `attribution_ready` 用于 `runtime_enabled`、`default_package_id`、`local_agent` 预览与 `binding_worker.start()`；失败时记录稳定事件（如 `attribution.preflight`，含 `error_code`，不含凭据/正文），不启动 worker、不 claim，保留排队绑定。
- **发布前置检查**：在 `deploy/release.sh` 读取 `.env` 后、迁移/切换 `current` 前，若 `HE_ATTRIBUTION_AGENT` 非空且 `command -v bwrap` 失败，则以明确信息退出，旧 release 继续服务。检查放在可测试的 helper 或可复用的 shell 函数中，避免只在 CI 外手工验证。
- **前端可见状态**：在 `apps/web/src/pages/evolution/targets/Index.vue` 增加页面级提示，`runtimeEnabled === false` 时说明“归因运行时不可用：未启用归因 Agent 或缺少 bubblewrap；已保存的绑定不会运行，修复后重启会自动开始”；在 `TargetTable.vue` 对 `attributionSkillName` 非空的目标显示“归因未运行”徽标。`apps/web/src/pages/overview/components/TargetsOverview.vue` 复用同一提示/徽标，并同步更新 `TargetFormDialog` 的旧提示文案。沿用现有 `/attribution-skill-packages` 的 `runtimeEnabled`，不新增 API 字段或契约。
- **文档**：`docs/deployment.md` / `.en.md` 增加“启用归因”小节：复用现有 AI Agent 配置（`HE_ATTRIBUTION_AGENT=provider`，不新增模型/密钥）、bubblewrap 前置、步骤（安装 bubblewrap、部署或改 `.env`、重启、观察日志）与验证（目标 owner/due、`attribute_output/<generation>`、页面报告）。`.env.example` 的 `HE_ATTRIBUTION_AGENT` 说明补上复用方式与 bubblewrap 前置链接。
- **测试**：API 单测覆盖“启用+缺 bwrap 时 `attribution_ready=false`、worker 不启动且不 claim”“启用+前置齐全时 worker 启动”“关闭时不做前置检查”；Deploy 测试覆盖 `AI_AGENT_PROVIDER` 非空时注入 `HE_ATTRIBUTION_AGENT=provider`、为空时 unset；Web 单测覆盖禁用时的提示/徽标；发布脚本检查补最小可执行测试（若无 shell 测试夹具，则提取 helper 做单测，不把未测试的 shell 条件写成已验证）。

## 实施步骤

1. Deploy 接线：在现有 AI Agent 注入步骤加入 `HE_ATTRIBUTION_AGENT=provider`（`AI_AGENT_PROVIDER` 非空时），为空时 unset；确认未新增 provider/model/key 配置。
2. 启动前置检查与 `attribution_ready` 接线 + API 单测。
3. 发布前置检查（helper/测试）并确认失败发生在切换 `current` 之前。
4. 前端提示/徽标 + 单测。
5. 更新部署文档双语、`.env.example` 说明与 Agent Note。
6. 生产机安装 bubblewrap、部署/重启，观察现有 generation 被领取并完成约 22 条；运行门禁与生产验收。

## 依赖与交付边界

- 依赖：无；本地归因 Agent、绑定 worker、现有 AI Agent 注入与 22 条待处理 Badcase 已存在。
- 交付边界：只加部署开关复用、前置校验、可见状态与文档；代码改动限制在 scope 内。生产启用是验收步骤，不由 API 自动开启，也不在应用进程内安装系统包。
- 非目标：不改变绑定/generation/due 语义，不改归因引擎、重试次数或报告格式；不新增第二套 AI Agent provider/model/API key；不新增 API 字段/契约；不修改 AI Agent provider/sandbox 实现；不写生产凭据或 Session 内容。

## 独立验证

```sh
pnpm test:api -- tests/test_attribution_preflight.py
pnpm test:gates
pnpm lint:api
pnpm typecheck:api
pnpm test
pnpm lint:web
pnpm typecheck:web
pnpm verify:docs
pnpm verify:flow
bash -n deploy/release.sh
```

- 单测证明：启用但缺 bwrap 时 `attribution_ready=false`、worker 不启动、目标行保持 `owner=NULL/failures=0`；前置齐全时 worker 启动；关闭时无前置错误。
- 前端单测证明：`runtimeEnabled=false` 时目标页出现提示、已绑定目标行出现徽标；`runtimeEnabled=true` 时不出现。
- Deploy 测试证明：`AI_AGENT_PROVIDER=claude-code` 时 `.env` 出现 `HE_ATTRIBUTION_AGENT=provider`，且没有新增第二套模型/密钥；`AI_AGENT_PROVIDER` 为空时该键被 unset。
- 发布检查在临时 `.env` 上以缺少 bwrap 的 PATH 运行时以非零退出，且未切换 `current`；文档/流程门禁全绿，`bash -n` 通过。
- 生产验证：部署/重启后 `attribution_owner` 在 2 秒内非空；`attribute_output/01M83TWE...` 出现；目标页显示约 22 条报告/分析；无需重新绑定。

## 验收标准

- Deploy 复用现有 AI Agent 配置：`AI_AGENT_PROVIDER` 非空时 `.env` 自动有 `HE_ATTRIBUTION_AGENT=provider`，且没有新增 Secret、provider、model 或 API key；`AI_AGENT_PROVIDER` 为空时归因关闭。
- 运行时关闭或缺少 bubblewrap 时，目标配置页与对象总览持续显示“归因运行时不可用，绑定不会运行”，已绑定行有可见徽标；不再只有编辑弹窗提示。
- 启用但缺 bubblewrap 时，启动日志给出稳定错误并跳过 worker，排队绑定不被 claim、失败次数不增加；发布前置检查在切换 `current` 前失败，旧 release 继续服务。
- 运行时与前置齐全时，现有 generation `01M83TWE...` 被自动领取并完成约 22 条 Badcase；目标页出现报告；无需重新绑定。
- 相关单测、前端测试、Deploy 测试、文档/流程门禁与 `bash -n` 通过；CI 全绿。

## 门禁与 CI

- `pnpm test:api`、`pnpm test:gates`、`pnpm lint:api`、`pnpm typecheck:api`、`pnpm test`、`pnpm lint:web`、`pnpm typecheck:web`、`pnpm verify:docs`、`pnpm verify:flow`。
- 若改动 `deploy/release.sh`，至少执行 `bash -n` 与聚焦前置检查测试；若改动 `.github/workflows/deploy.yml`，补 Deploy 注入测试并确认 `AI_AGENT_PROVIDER` 缺失/空值时不会残留旧开关。
- 提交与 PR 标题含本 issue 编号；不在仓库写入生产凭据、Session 内容或私有数据。

## 非目标

- 不新增第二套 AI Agent provider/模型/API key 配置；复用 `AI_AGENT_PROVIDER` 与共享 CLI/settings/key。
- 不在 `Settings` 中把 `attribution_agent` 默认值硬编码为 `provider`；是否启用由 Deploy 注入或显式覆盖决定。
- 不在 API/部署脚本中自动安装系统包；缺 bubblewrap 时只失败并给出安装指引。
- 不改变绑定保存、generation、due、重试或删除排队绑定的语义，不改归因引擎、报告格式、模型或 Skill 内容。
- 不新增 API/契约字段，不改健康检查响应结构；不修改 AI Agent provider/sandbox 的既有实现。
- 不写生产凭据、Session 内容或私有数据。
