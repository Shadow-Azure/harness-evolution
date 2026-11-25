# AI Agent 后端可替换：中立技能布局、显式能力协议与通用配置入口

[English](bugfix-ai-agent-portable-backend.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-57
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/app/service/evolution/local_attribution.py
  - apps/api/app/service/evolution/patch_source.py
  - apps/api/app/config.py
  - apps/api/app/main.py
  - apps/api/tests/**
  - docs/**
  - plans/**
  - .agents/**
  - attribute/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 604
  url: https://github.com/Shadow-Azure/harness-evolution/issues/604
```

## 背景

### 问题描述

出站层 `third_party_api/ai_agent` 的文档与设计都宣称「换一个 AI agent 只加一个子类与一个注册项」（`docs/ai-agent.md` 分层节、07 §5.5.1），但 2026-11-25 对 `origin/main @ 2952c5f4` 的逐操作审计表明，该说法只在「只跑 analyze / edit_workspace / health_check」的前提下成立。若要求 Skill / 归因能力随 provider 一起切换（提出人的明确要求），当前至少有三处厂商假设泄漏在子类之外：

- **技能布局与调用语法写在服务层**：`service/evolution/local_attribution.py` 的 `_stage_attempt` 把冻结技能铺到 `work/.claude/skills/<name>` 并建 `.cac/skills` 别名，执行 prompt 写死斜杠命令 `/{name} input_badcase.json，请分析并生成归因报告`。斜杠命令能被解析，前提正是文件铺成了 Claude 认识的形状；一个不识别 `.claude/skills`、没有斜杠命令机制的 CLI agent 即使实现了 `run_skill`，也拿不到技能包。
- **配置命名空间绑定 Claude**：`app/config.py` 只有 `ai_agent_claude_bin` / `ai_agent_claude_settings` 两个具名字段（且空 bin 启动红）；新后端的二进制与 settings 路径没有类型化的配置入口，只能读裸 env 或改 `Settings` 代码。
- **能力靠隐式推导、鉴权不在契约里**：`base.py` 的 `supports_skills` 用「`run_skill` 是否被覆盖」反推，新子类忘实现 `run_skill` 时归因**静默**降级为 cache-only（启动仅一条 warn）；`ProviderHealth` 只有 `healthy` + 自由文本 `detail`，Claude 未配置凭据时仍报 `healthy=True`，鉴权状态只在启动日志里，`/api/health` 不含 provider 状态。

此外两处次要契约债一并处理：编辑提交文件名在子类（`claude_code.EDIT_PLAN_FILENAME`）与 `patch_source._edit_prompt` 字面量各存一份；`base.py` 导出 Claude 专用常量 `PERMISSION_MODE`。

### 分析过程（2026-11-25 封装度审计）

审计把「一个 agent 接入要承担的操作」拆成六层（契约/调用面/传输协议/运行时配置/生命周期观测/交付）逐层判定。结论：模型出站这一层封装成立——argv、进程组生命周期、输出解析、usage 归一、权限规则、错误分类全部落在厂商侧（`claude_code.py` 1,280 行 + `claude_skill.py` 296 行），父类仅 3 个抽象方法，业务层无后端分支（仅 `config.py` 失败策略按 `fake` 推导、`local_attribution.py` 重放别名两处）；但运行时配置、鉴权状态、技能布局、交付四条未封进子类，「只加一个子类」在场景 A（只要 analyze/edit/health）成立，在场景 B（Skill/归因随 provider 切换）不成立，须先改服务层。完整审计工作稿见分支 `analysis/ai-agent-provider-audit` 的 `plans/ai-agent-provider-encapsulation-audit.html`（未入库，结论已吸收进本 issue）。

重放校验的事实核查：`freeze()` 在绑定时刻把 `agent`（当时 `provider_id`）与 `modelIdentity`（当时环境推导）写进 manifest 并固化 hash 进 run/target；此后每次归因 case 执行（含重启后 `jobs.recover()` 补跑、失败重试、归因 eval）都会按冻结 manifest 解析 provider 并重算身份比对（`local_attribution.py:555-557`）。因此旧快照重放是承重路径：`_skill_provider` 的 `{"claude", "...ClaudeBackend"} → "claude-code"` 别名映射必须保留；新后端的 `skill_model_identity` 返回值必须遵循现有形状约定（`dict[str, str]`，`selector`/`model`/`endpointHash` 或 `selection: provider-default`），保证跨 provider 可比。

### 与提出人的讨论过程与结论（2026-11-25）

- **Q1 换什么**：换 CLI agent（不是直连模型 API）。`claude_cli.py` 的子进程传输与 `submission.py` 的结构化提交通道继续可用。
- **Q2 Skill/归因是否随 provider 切换**：必须。因此本 issue 的核心是技能路径 provider 化。
- **Q3 配置入口**：走 env，`Settings` 支持 `ai_agent_bin` / `ai_agent_settings` 通用字段，旧名 `ai_agent_claude_bin` / `ai_agent_claude_settings` 保持兼容读取（别名），不破坏现有部署注入。
- **Q4 部署**：部署流水线不在本 issue 范围；真要换 agent，提出人自行同步修改部署侧。
- **Q5 能力声明**：升格为显式协议——父类新增 `capabilities` 类变量；`ProviderHealth` 增加结构化鉴权字段；preflight 输出能力行。未声明 `capabilities` 的旧子类保留「按 `run_skill` 覆盖推导」的兼容路径。
- **prompt 归属**：讨论过「服务层继续拼 `/{name}` prompt、子类只管铺盘」是否可行，结论是不行——铺盘布局与调用语法是同一协议的两半，服务层若继续写 `.claude/skills` 并拼斜杠命令，等于要求每个新后端模拟 Claude 协议。最终采纳**中立技能布局**：平台定义 `work/skills/<name>/` 布局，上游 prompt 改为引用该路径（不再含斜杠语法）；provider 通过 `stage_skill` 钩子把中立布局适配成自己最优形态，并可返回可选的「原生前缀」——`ClaudeCodeProvider` 建 `.claude/skills/<name>` 软链并返回 `/{name} `（保留原生技能触发的确定性），通用后端返回空串即可零适配接入。
- **旧快照与 prompt 措辞**：prompt 不在冻结范围内，改为路径引用后旧快照补跑也会用新 prompt；agent/modelIdentity 校验不受影响，视为可接受的执行语义演进，在实现 PR 的 Agent Note 里记录。

### 提出人的要求

- 换 CLI agent 时，**Skill / 归因能力必须随 provider 一起切换**，不允许「新后端暂不跑归因」的中间态。
- 配置走 env：支持 `ai_agent_bin` / `ai_agent_settings`，旧 `ai_agent_claude_*` 兼容。
- 能力升格为显式协议。
- 部署流水线由提出人在切换时另行修改，不在本 issue 内。
- 重放校验与旧快照别名映射保持现状语义，不得因本次改造破坏存量快照的重放。

## 目标

- `AIAgentProvider` 新增 `stage_skill(work, name, files) -> str` 钩子：provider 把 `work/skills/<name>/` 的中立布局适配为自己的技能形态，并返回可选的调用前缀；服务层不再出现 `.claude/skills`、`.cac/skills` 与 `/{name}` 字面量。
- 上游技能 prompt 改为「使用 {name} skill：读取 `skills/{name}/SKILL.md` 并严格遵循……」的路径引用形态；任务文本（`INSTRUCTIONS`、输入文件说明、平台 writer 契约）保持在上游。
- `AIAgentProvider` 新增 `capabilities: ClassVar[frozenset[str]]` 显式能力声明（`"analyze"`、`"edit"`、`"skill"`），`supports_skills` 优先读声明，未声明时保留按 `run_skill` 覆盖推导的兼容；`ProviderHealth` 新增 `auth`（`ok` / `missing` / `unknown`）结构化字段，`preflight` 输出 provider 能力行。
- `Settings` 新增 `ai_agent_bin` / `ai_agent_settings` 通用字段，旧 `ai_agent_claude_bin` / `ai_agent_claude_settings` 作为兼容别名继续可读；`AIAgentProvider` 新增 `from_settings()` 类方法钩子，需要额外配置的后端在其中解析自己的命名空间。
- 顺手项：`EDIT_PLAN_FILENAME` 提升为 `ai_agent` 包共享常量（`patch_source.py` 同步收敛，`_edit_prompt` 的字面量改为引用它）；`PERMISSION_MODE` 常量从 `base.py` 下移到 `claude_code.py`。
- 更新 `docs/ai-agent.md` / `.en.md` 的「新增后端只加一个子类与注册项」表述，写清换后端的实际触点；补 Agent Note。

## 设计依据

- [07 §5.5.1 AI Agent Provider 出站适配层](../../../plans/fullstack-design/07-backend-implementation.md)：父类只定契约、能力面按接口而非厂商划分、未来换 OpenCode 或直连模型 API 只新增子类；本 issue 把该节宣称的「只加子类」落地为真实可替换，并同步修订该节关于扩展位的描述（`SupportsEmbedding` 等仍未实现，不在本 issue）。
- [07 §5.5.3 结构化提交通道](../../../plans/fullstack-design/07-backend-implementation.md)：提交通道是协议而非厂商机制，所有 CLI 后端共享；本 issue 不改其语义。
- [07 §5.5.4 Edit 指令式 patch](../../../plans/fullstack-design/07-backend-implementation.md)：EditPlan 提交文件名是跨层契约，收敛为共享常量。

## 实现内容

- `third_party_api/ai_agent/base.py`：新增 `stage_skill(work, name, files)`（默认抛「provider does not support Skill staging」）、`capabilities` 类变量（默认含 `analyze`/`edit`）、`from_settings()` 类方法（默认 `cls(settings)`）；`supports_skills` 改为「声明优先、覆盖推导兜底」；`PERMISSION_MODE` 移出本模块。
- `third_party_api/ai_agent/claude_code.py`：实现 `stage_skill`（铺中立布局文件 + 建 `.claude/skills/<name>` 软链 + 返回 `/{name} ` 前缀）、`capabilities` 显式声明、`from_settings` 读取通用字段与旧名兼容；承接 `PERMISSION_MODE`。
- `third_party_api/ai_agent/contracts.py`：`ProviderHealth` 增加 `auth` 字段（`ok` / `missing` / `unknown`）；`EDIT_PLAN_FILENAME` 落为本包共享常量。
- `service/evolution/local_attribution.py`：`_stage_attempt` 瘦身为「写 case 输入 → 调 `provider.stage_skill` → 拼前缀 + 任务文本」；重放别名映射与 `skill_model_identity` 相等校验保持现状语义；执行日志仍记录完整最终 prompt。
- `app/config.py`：新增 `ai_agent_bin` / `ai_agent_settings`，校验规则沿用旧名（空 bin 启动红、空 settings 视为 unset）；旧字段保留并标注 deprecated，读取处统一经兼容访问器归一。
- `app/main.py` 与 `ai_agent/preflight.py`：装配改经 `from_settings()`；preflight 输出能力行（`provider=... skills=yes/no auth=ok/missing/unknown bin=present/missing`）。
- `fake.py`：声明 `capabilities`（无 `skill`），作为显式协议的最小样例。
- 测试：`stage_skill` 布局与前缀、兼容后端的零适配接入、`capabilities` 显式/推导双路径、`ProviderHealth.auth` 三态、Settings 新旧名等价、服务层瘦身后的技能执行与旧快照重放（含 `claude` 旧名别名）回归。
- 文档与流程：`docs/ai-agent.md` / `.en.md` 更新触点清单与能力协议；`plans/fullstack-design/07-backend-implementation.md` §5.5.1 补记能力协议与技能布局契约；实现 PR 同 PR 补 Agent Note。

## 实施步骤

1. `base.py` / `contracts.py`：新增 `stage_skill`、`capabilities`、`from_settings`、`ProviderHealth.auth`、共享 `EDIT_PLAN_FILENAME`；`PERMISSION_MODE` 下移。
2. `claude_code.py` / `fake.py`：实现钩子与显式声明；`from_settings` 的新旧名兼容归一。
3. `config.py`：新增通用字段与兼容访问器；`main.py` / `preflight.py` 接入。
4. `local_attribution.py`：`_stage_attempt` 瘦身与 prompt 形态切换；保持重放别名与身份校验语义。
5. 补齐单测与 API 测试（含中立布局执行、零适配兼容后端、旧快照重放回归）。
6. 跑聚焦门禁；更新 `docs/ai-agent.md` / `.en.md`、07 §5.5.1 与 Agent Note；`flow:sync` 流转状态。

## 依赖与交付边界

- 依赖：无未完成前置（`bugfix-17`/`bugfix-19`/`bugfix-21`/`bugfix-26` 等已 done）。
- 交付边界：只改 `ai_agent` 包、`local_attribution.py` 的技能装配段、`config.py` / `main.py` / `preflight`、测试与文档；不改 `submission.py` / `edits.py` 协议、不改 `claude_cli.py` 传输语义、不改 `_skill_provider` 别名与 modelIdentity 校验逻辑、不改评测与聚类业务。

## 独立验证

```sh
pnpm lint:api
pnpm typecheck:api
pnpm test:api -- -k "ai_agent or local_attribution or preflight"
pnpm test:api:serial -- -k "attribution"
pnpm verify:flow
pnpm lint:docs
```

- 预期：`ClaudeCodeProvider.stage_skill` 在任务目录同时产出中立布局与 `.claude/skills/<name>` 软链并返回 `/{name} ` 前缀；一个只声明 `capabilities` 的 stub 后端零斜杠适配即可通过技能执行用例；`ai_agent_bin` 与 `ai_agent_claude_bin` 任意一个生效时 provider 解析到同一路径，两者同时存在时通用名优先；`ProviderHealth.auth` 三态按凭据存在性正确返回；preflight 输出能力行；`claude` 旧名快照重放用例不变绿转红。

## 验收标准

- 服务层 `local_attribution.py` 不再包含 `.claude/skills`、`.cac/skills`、`/{name}` 字面量；技能铺盘与调用语法完全由 provider 决定。
- 新增一个最小 stub 后端（声明 `capabilities`、实现 `stage_skill` 返回空前缀、复用 `claude_cli` 传输）即可在测试内完成 analyze / edit / health / skill 四能力执行，全程不改服务层与配置代码。
- `supports_skills` 缺失能力不再静默：未声明且未覆盖 `run_skill` 的后端在 preflight 输出 `skills=no`，装配行为与现状一致（归因 cache-only），但能力可枚举。
- `ai_agent_bin` / `ai_agent_settings` 生效且旧名兼容：仅设旧名、仅设新名、两者并存三种 env 组合下行为确定并有测试覆盖。
- 重放语义不回归：`{"claude", "...ClaudeBackend"} → "claude-code"` 别名与 `skill_model_identity` 相等校验保持现状；存量快照（含旧名）用例通过。
- `ProviderHealth.auth` 结构化字段与 preflight 能力行落地；`/api/health` 是否并入 provider 状态不在本 issue（见非目标）。
- 聚焦测试、`verify:flow`、`lint:docs` 通过；`docs/ai-agent.md` / `.en.md` 双语更新且配对重录；Agent Note 已补。

## 门禁与 CI

- 命中：`pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api`、`pnpm test:api:serial`、`pnpm verify:flow`、`pnpm lint:docs`（实现 PR 另跑 `pnpm verify:docs` 与 `pnpm test:gates`）。
- 不新增第三方依赖；CI 全程 fake / stub provider，不触网、不依赖真实 `claude` 二进制；`HE_AI_AGENT_CLAUDE_E2E=1` 的真实 CLI 冒烟仍为可选 lane，新增用例覆盖中立布局 prompt 形态。

## 非目标

- 不实现真实的新后端（Codex / Gemini 等）；只保证「新增子类 + 注册 + 零服务层改动」的接入面成立，stub 后端测试即为验收载体。
- 不改部署流水线、安装脚本、Secrets 注入与 `docs/claude-code.md`（提出人在真实切换时另行处理）。
- 不改 `submission.py` 提交协议、`edits.py` 应用器、`claude_cli.py` 传输与超时常量语义；不引入 per-provider 超时配置与 `HE_AI_AGENT_NATIVE_SCHEMA` 快路径。
- 不清理 `EditResult.changed_files` / `unified_diff` 等恒空契约字段（另行评估）。
- 不把 provider 健康并入 `/api/health`；不实现 `SupportsEmbedding`；不改归因 eval 与聚类三层业务逻辑。
