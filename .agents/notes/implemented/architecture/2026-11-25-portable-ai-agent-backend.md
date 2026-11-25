# Agent Note: AI Agent 后端可替换——中立技能布局、显式能力协议与通用配置入口

Status: implemented

[English](2026-11-25-portable-ai-agent-backend.en.md) | 中文

## Problem

出站层 `third_party_api/ai_agent` 在文档与 07 §5.5.1 里宣称「换一个 AI agent 只加一个子类与一个注册项」，但逐操作审计表明这只在「只跑 analyze / edit / health」时成立。提出人要求 Skill / 归因能力随 provider 一起切换，而当时至少三处厂商假设泄漏在子类之外：技能铺盘布局（`.claude/skills` + `.cac/skills` 别名）与调用语法（`/{name}` 斜杠命令）写在服务层 `local_attribution.py`；配置命名空间绑定 Claude（只有 `ai_agent_claude_bin` / `ai_agent_claude_settings`）；能力靠「`run_skill` 是否被覆盖」隐式推导，鉴权状态不在契约里（`ProviderHealth` 只有 `healthy` + 自由文本，Claude 无凭据仍报 healthy）。一个不识别 `.claude/skills`、没有斜杠机制的 CLI agent 即使实现了 `run_skill` 也拿不到技能包。

## Decision

- **中立技能布局 + `stage_skill` 钩子**：平台定义 `work/skills/<name>/` 中立布局，上游任务文本改为路径引用形态（不含斜杠语法）；provider 在 `stage_skill` 里把中立布局适配成自己的形态并返回可选原生前缀。`ClaudeCodeProvider` 建 `.claude/skills/<name>` 链接（Windows 无符号链接权限时回退整树复制）并返回 `/{name} `，通用后端返回空串即可零适配接入。服务层 `_stage_attempt` 瘦身为「校验冻结文件 → 调 `stage_skill` → 平台 writer 契约换写 → 写 case 输入」，不再出现任何厂商字面量。
- **能力升格为显式协议**：`capabilities: ClassVar[frozenset[str]]`（`analyze`/`edit`/`skill`）声明优先；未声明的旧子类保留「按 `run_skill` 覆盖推导」兼容路径。`ProviderHealth.auth`（`ok`/`missing`/`unknown`）进契约，preflight 输出 `provider=… skills=… auth=… bin=…` 能力行（`bin=present` ⇔ `auth ∈ {ok, missing}`，即探测到可用二进制）。
- **配置通用入口**：`Settings` 新增 `ai_agent_bin` / `ai_agent_settings`（通用名以 `None` 表「未设置」），读取统一经 `effective_ai_agent_bin` / `effective_ai_agent_settings` 归一——仅旧名、仅新名、并存=新名优先三种组合行为确定；旧 `ai_agent_claude_*` 保留为 deprecated 别名，校验规则沿用旧名（空 bin 启动红、空 settings 视为 unset）。装配统一经 `from_settings()`。
- **顺手契约债**：`EDIT_PLAN_FILENAME` 收敛为 `contracts.py` 包级共享常量（`claude_code` re-export 保持旧导入路径）；`PERMISSION_MODE` 从 `base.py` 下移至 `claude_code.py`。

## Alternatives considered

- **服务层继续拼斜杠 prompt、子类只管铺盘**：铺盘布局与调用语法是同一协议的两半，服务层若继续写 `.claude/skills` 并拼 `/{name}`，等于要求每个新后端模拟 Claude 协议。拒绝。
- **`base.stage_skill` 默认实现「写中立布局 + 空前缀」**：能让通用后端真正零实现接入，但默认抛错（`provider does not support Skill staging`）与 `supports_skills` 的显式化方向一致——缺失能力应显式暴露而非静默降级（本 issue 的动机之一就是静默降级教训）。通用后端自己写五行零适配实现。拒绝默认实现。
- **通用 bin 字段带默认值、用「值 ≠ 默认」判断是否设置**：旧名与新名默认值相同，值比较无法区分「显式设为默认」与「未设置」。通用名用 `str \| None = None` 精确保存来源信息，三种组合严格可判定。拒绝值比较。
- **preflight 为能力行新增结构化二进制字段**：`auth=unknown` 已蕴含「探测未到达可用部署」，`bin` 由 `auth` 推导即可，不为一个展示 token 扩契约。拒绝加字段。
- **给 `AgentBackend`（legacy 插件基类）补 `stage_skill`**：该文件不在本 issue scope；且遗留插件快照的唯一在库身份已由 `{"claude", "...ClaudeBackend"} → "claude-code"` 别名覆盖。任意 `module:Class` 插件快照补跑现会在铺盘前得到显式错误，属可接受语义演进。拒绝越 scope。

## Consequences

- 旧快照补跑沿用新任务文本：prompt 不在冻结范围，`agent` / `modelIdentity` 校验不受影响，视为可接受的执行语义演进；`{"claude", "...ClaudeBackend"} → "claude-code"` 别名与 `skill_model_identity` 相等校验语义完全不变，存量快照（含旧名）用例保持绿。
- case-tools 模式（Linux 关 bwrap）改从中立布局读取冻结 `SKILL.md`：`attribution_case_tools` 与 `claude_skill._case_tool_options` 的反软链逃逸守卫只在中立布局（全真实文件）上执行，厂商链接仅供 CLI 自身的技能发现。
- preflight 现在会以 ≤10s 超时探活 provider（真实后端执行一次 `--version`）：能力行的 `auth`/`bin` 来自这次探测，发布脚本的既有判定 token（`ready=True` / `cache_only=True` / `ATTRIBUTION_*`）保持不变。
- `docs/ai-agent.md` 词数预算从 850 提至 1000：触点清单、能力协议与通用配置名是常驻事实，压缩会丢掉「换后端要碰什么」的可操作性。
- 部署侧切换真实新后端时仍需同步部署流水线与 Secrets 注入（提出人自理，本 issue 不动 `deploy/`）。
