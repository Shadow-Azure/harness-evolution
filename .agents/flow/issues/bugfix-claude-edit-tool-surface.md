# agent-edit 补丁生成在 bare 工具面下无法提交 EditPlan：统一 edit 与 analyze 的调用形状

[English](bugfix-claude-edit-tool-surface.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-47
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - apps/api/app/third_party_api/ai_agent/claude_code.py
  - apps/api/tests/**
  - docs/**
  - plans/**
  - .agents/**
adr: [../../notes/implemented/bug-fix/2026-11-24-claude-edit-tool-surface.md]
github:
  number: 566
  url: https://github.com/Shadow-Azure/harness-evolution/issues/566
```

## 背景

2026-11-24 09:41–09:52（CST），生产 full run `01M85KA28DRPZ9RN26A3GV5JQ2`（skill `codespec-subagent-driven-development@openspec-cn-main-copy-ar-a7ec200-claude-core`）在第 6/7 步「迭代优化」第 1/3 轮的补丁生成阶段阻塞：

```text
运行在补丁生成（patch）阶段阻塞
claude-code edit call exited unsuccessfully: exit_code=1;
stderr=[claude-code:unrecognized_model] {"model":"MiniMax-M3.1-Flash[1m]","query_source":"sdk"}
```

- run 页面：`http://8.149.232.63/workspaces/01M7KJ05ENF9784GPBDV544VB0/evolution/runs/01M85KA28DRPZ9RN26A3GV5JQ2`
- `status=blocked`、`blockedStage=patch`、`retryAttempts=0`、`nextRetryAt=null`，失败时间 `2026-11-24T09:52:30+08:00`。

### 问题描述

同一 run 的持久事件（`GET /api/evolution/runs/{id}/events`）给出了完整时间线：

| seq | 时间 | 事件 | 关键字段 |
|---|---|---|---|
| 7 | 09:39:24 | `ai_agent_call` `cluster.review` ok | `model=MiniMax-M3.1-Flash[1m]`、`costUsd=0.0509`、`latencyMs=8977`、tokens>0 |
| 8 | 09:39:44 | `ai_agent_call` `cluster.score` ok | 同模型、`latencyMs=20164`、tokens>0 |
| 9 | 09:41:40 | `ai_agent_call` `severity.score` ok | 同模型、`latencyMs=115335`、tokens>0 |
| 11 | 09:41:46 | `workspace_prepared` | `cacheHit=true`、`baseCommit=59bebcf`、分支 `evo/20261124-01M85KA28DRPZ9RN26A3GV5JQ2` |
| 12 | 09:52:30 | `ai_agent_call` `agent.edit` **error** | `model=unknown`、`costUsd=0`、`sessionId=null`、tokens=0、`latencyMs=0` |
| 13 | 09:52:30 | `run_blocked` | `error.type=AgentProviderError`、`payload.retryable=true`、`stage=candidate` |
| 14 | 09:52:30 | `run_blocked` | `detail=exit_code=1; stderr=[claude-code:unrecognized_model] {"model":"MiniMax-M3.1-Flash[1m]","query_source":"sdk"}` |

由此可以确定三件事：

1. **同 run、同模型、同 settings 的 analyze 调用全部成功**（seq 7–9）。`[claude-code:unrecognized_model]` 只是 Claude Code 对未在已知清单里的自定义模型 ID 打到 stderr 的诊断行（官方文档明确把它列为诊断行，并给出用 `modelOverrides` 消除的办法），它不是失败原因；把它当成原因是排障被带偏的结果。
2. **edit 子进程真实存活约 644 秒**（09:41:46 → 09:52:30），既不是 `could not start`（毫秒级），也不是 `cancelled`（超时/取消走另一条归类），而且远未到 `EDIT_TIMEOUT_SECONDS=1800`。也就是说 CLI 正常启动、跑了一段很长的对话，最后以 `exit_code=1` 自己退出。
3. **这次调用没有产生任何可用结果**：`AgentUsage` 全 0、`sessionId=null`、`model=unknown`，提交的 `EditPlan` 文件不存在，因此 patch 生成失败、run 阻塞在 `stage=patch`。

### 根因分析过程

1. **读生产证据**：上面的错误来自 `ClaudeCodeProvider._call()` 的 `claude-code {phase} call exited unsuccessfully` 分支（`claude_code.py:477-483`），`phase="edit"`，`detail` 由 `_diagnostics(result)` 只拼 `exit_code` 与**有界 stderr**（`claude_code.py:1019-1025`）。CLI 的 JSON stdout（`--output-format json` 的 result 文档）在这条路径上被整体丢弃。
2. **读 edit argv**：`_edit_argv()`（`claude_code.py:581-612`）仍然是 `--bare … --allowed-tools Read,Grep,Glob,Write(./.harness-evolution/edits.json5)`；allow 规则来自 `SubmissionPrep.allowed_tools`，固定派生为 `Write(./<relative>)`（`submission.py:262`）；`collect()` 只读这个文件（`submission.py:267-296`）。
3. **对照同仓已修的 analyze 路径**：提交工具面在 #537（提交 `de7128c9`）已经修过一次，`_analyze_argv()` 现在是 `--safe-mode --restricted --strict-mcp-config --tools Read,Write --allowed-tools Read(//<abs>),Edit(//<abs>) --output-format stream-json --verbose`，并且 `_ensure_submission_tool()` 会在 `system/init.tools` 缺少 `Write` 时直接失败（不重试）。那次 Agent Note 明确写着「edit 通道不在本 issue 的契约内，argv 保持原样」，`bugfix-cluster-review-file-submission` 的非目标也写了「edit 通道若启用仍需单独验证其工具面」。
4. **工具面**：#537 在同一台部署机、同一 CLI `2.1.323` 上实测：`--bare` 把可用工具收窄为 `Bash/Edit/Read`，**没有 `Write`**；`--bare --tools "Read,Write"` 也只返回 `Read`，加不回来。edit 路径同样带 `--bare`，所以它同样写不出提交文件。
5. **权限规则**：即使去掉 `--bare`，`Write(./relative)` 也不参与 Claude Code 的文件写权限匹配——文件写只认 `Edit(path)` 规则，并且要匹配本次调用的绝对路径。#537 的对照实验已经证明「相对路径 + Write 规则」两个面都不成立。
6. **为什么 644 秒后 exit 1**：模型没有可用的写工具，只能反复尝试被 `dontAsk` 拒绝的 `Bash`/`Edit`、或反复读文件，直到 `--max-turns 40` 用尽；print 模式下轮次用尽是 `is_error=true` 的 result，CLI 以退出码 1 结束。精确的 `subtype`（`error_max_turns` 或其它）今天无法取证，正是因为第 1 步发现的 stdout 被丢弃；但无论具体 subtype 是哪一种，**没有写工具就意味着 `edits.json5` 永远写不出来，这条通道必然失败**，644 秒只是它失败的耗时形态。
7. **排除项**：模型名与网关正常（同模型三次 analyze 成功）；凭据正常（analyze 已鉴权成功）；workspace 正常（seq 11 `cacheHit=true`）；不是超时（644s < 1800s，且未归类 `cancelled`）；不是进程起不来（`could not start` 会发生在数毫秒内且 detail 不同）。

### 结论

- **直接原因**：edit 调用没有产出 `.harness-evolution/edits.json5`，模型在 `--max-turns 40` 内耗尽轮次，CLI 以 `is_error` 退出 1；provider 把它归一成 `exited unsuccessfully`，patch 生成失败，run 阻塞在 `stage=patch`。
- **根因**：`ClaudeCodeProvider` 的 edit 通道保留了 #537 之前的两处缺陷，二者在同一处：① `--bare` 让工具集没有 `Write`；② 提交通道的 allow 规则是相对路径的 `Write(./…)`，而 CLI 只按 `Edit(绝对路径)` 匹配文件写。analyze 已经修好，edit 是明确留下的未修面，且 edit 从未跑过真实 CLI 冒烟。
- **为什么看起来像模型问题**：`_call()` 在非零退出时丢弃 stdout result、只报 stderr，而 `unrecognized_model` 是唯一写进 stderr 的行，于是诊断行冒充了错误原因；这同时让「四个 0 + 644 秒」的真实失败形态不可见。
- **容量性缺陷（与根因分开处理）**：`EDIT_MAX_TURNS=40` 对真实 edit 会话偏紧——本次 644 秒 ≈ 40 轮 × 16 秒就打满了。工具面修好之后，探索 + 写计划仍会超过 40 轮，所以轮次预算必须同步提高；但提上限不能替代工具面修复，工具面不可用时轮次再多也提交不了，只会把失败拖到墙钟上限。

## 目标

- 让 edit 通道在生产 CLI 上真正可用：模型能在工具集中看到并调用写工具，权限规则能匹配本次 workspace 的提交路径，`edits.json5` 被写出并通过 `submission.collect` 校验。
- 让 edit 与 analyze 共用**同一套已验证的调用形状**，并且由同一个子类私有函数 `_headless_argv()` 构造 argv、同一套规则构造与失败证据；不再维护第二套 argv 与第二套权限规则。
- 其它调用点（`health_check()`、`run_skill()`）保持有据可查的例外，但共用 binary / settings / 失败证据这些适配层规则。
- 让 edit 的失败在调用结束时即可诊断（进程退出后）：缺 `Write`、提交路径被拒、轮次用尽都要指出具体原因，而不是 644 秒后只给一行模型诊断。
- 把 edit 的轮次预算调到真实会话够用的水平（`EDIT_MAX_TURNS` 40 → 120），同时保留 `EDIT_TIMEOUT_SECONDS=1800` 作为墙钟上限，花费防护不因此移除。
- 生产验收：一次真实 full run 的第 6 步进入 candidate，`agent.edit` 为 `outcome=ok`、tokens>0、model 非 `unknown`。

## 设计依据

- [07 §5.5.1 AI Agent 能力面](../../../plans/fullstack-design/07-backend-implementation.md)：工具面与权限模式属于 provider 适配层，不渗入业务层；子类对同一能力的调用形状应一致。
- [07 §5.5.3 六层 JSON 可靠性](../../../plans/fullstack-design/07-backend-implementation.md)：一次性任务目录 + 唯一写工具 + 严格/JSON5/repair 解析 + Pydantic 校验，是跨后端提交契约；`collect()` 只读那一个文件。
- [07 §5.5.4 执行流与安全闸](../../../plans/fullstack-design/07-backend-implementation.md)：edit 的只读探索、EditPlan 提交、临时镜像确定性应用与 `--max-turns` 花费防护。
- [#537 修复记录（Agent Note）](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/bug-fix/2026-11-23-claude-analyze-tool-surface.md)：`--bare` 无 `Write`、`Write(相对路径)` 不匹配、必须用 `Edit(绝对路径)` 的三条实测结论，以及 analyze 的最终 argv 形状。
- [Claude Code 模型配置文档](https://code.claude.com/docs/zh-CN/model-config)：`[claude-code:unrecognized_model]` 是自定义模型 ID 的诊断行，可用 `modelOverrides` 消除，与调用失败无关。

## 实现内容

**唯一推荐方案：让 edit 直接复用 analyze 已验证的调用形状与失败证据链，并把轮次预算提到真实会话够用的水平**，一次改完，四件事不可拆：

1. **argv 与工具面**：`_edit_argv()` 去掉 `--bare`，改成与 `_analyze_argv()` 相同的硬化参数——`--safe-mode --restricted --strict-mcp-config`，用 `--tools Read,Write` 把内置工具收缩到「读工作区 + 写提交文件」两项；`--output-format stream-json --verbose` 取代 `json`，以便拿到 `system/init.tools` 与 result 的 `is_error`/`subtype`/`num_turns`/`stop_reason`/`permission_denials`；`--no-session-persistence`、`--permission-mode dontAsk` 与 `--settings` 保持现状；`--max-turns` 按第 4 点提高。`Grep`/`Glob` 只有在 init 工具列表证明存在时才加进 `--tools`（Linux 默认集不含这两个），不靠 allowlist 猜。
2. **提交权限**：edit 的 `--allowed-tools` 不再使用 `prep.allowed_tools` 的 `Write(./…)`，改由 `prep.result_path` 的绝对路径构造 `Edit(//<abs>/.harness-evolution/edits.json5)`（复用 `_permission_rule_path()`），需要读的路径同法给 `Read(//<abs>)`。`submission.py` 的 schema/collect/retry 契约不动，只换 provider 适配层传给 CLI 的规则。
3. **失败证据**：`_call()` 在 `returncode != 0` 时先用已解析的 result 组装 detail——`is_error`/`subtype`/`api_error_status`/`num_turns`/`stop_reason`/`permission_denials`，再附有界 stderr；复用 `_ensure_submission_tool()`，在 `system/init.tools` 缺 `Write` 时于调用结束时（进程退出后）抛错（`retryable=false`、不重试），不再烧满 40 轮。`_diagnostics()` 不再把 stderr 当唯一证据。
4. **轮次预算**：`EDIT_MAX_TURNS` 从 40 提到 120（常量在 `claude_code.py:101`，argv 在 `:605` 使用）。40 轮对真实 edit 会话偏紧——本次 644 秒就是 40 轮 × 约 16 秒打满；120 轮按同一观测约 32 分钟，会先撞上**未改动的** `EDIT_TIMEOUT_SECONDS=1800`，所以墙钟仍是主护栏，轮次上限退化为安全网：健康会话有足够余量，退化会话最迟在 1800s 被 SIGINT→SIGKILL 收口。提上限只增加容量，不能替代第 1、2 点——工具面不可用时轮次再多也写不出提交文件。

**调用形状统一（同一个子类私有函数）**：把 `-p` 无头调用的形状收进 `ClaudeCodeProvider._headless_argv()`，`_analyze_argv()` / `_edit_argv()` 只装配各自的参数差异，不再各自拼 argv：

| 调用点 | 现状 | 处理 |
|---|---|---|
| analyze `_analyze_argv()` | 已是 #537 的硬化形状 | 改为调用 `_headless_argv()`：task 目录 cwd、`--tools Read,Write`、一次性提交路径 |
| edit `_edit_argv()` | 仍是 `--bare` 旧形状 | 改为调用 `_headless_argv()`：workspace cwd、同一套提交规则、`--max-turns 120` |
| `health_check()` | 只跑 `--version` | 保持例外：没有 prompt，套不进 `-p` 形状；继续共用 `_binary()` / `_settings_file()` |
| `run_skill()`（`claude_skill.run`） | bwrap/sandbox-exec + `--bare --session-id --output-format json --permission-mode bypassPermissions` | 保持例外：沙箱、私有 HOME、固定 session、stdout 取结果是它的契约；只共用 `_binary()` / `_settings_file()` 与失败证据归一 |

`_headless_argv()` 拥有：binary、`--safe-mode --restricted --strict-mcp-config`、`-p <prompt>`、`--output-format stream-json --verbose`、`--permission-mode dontAsk`、`--tools`、`--allowed-tools`、`--no-session-persistence`、可选 `--max-turns`、可选 `--settings`。提交规则由同一个 `_submission_rules()` 生成（绝对 `Read(//…)` / `Edit(//…)`），失败证据由同一个 `_call()` 归一。两处都不允许再各自拼参数——edit 能长期留着 `--bare` 而 analyze 早已修好，正是缺少唯一构造函数的结构性后果。

为什么 skill 不并进来：它的 `--bare` 是沙箱内「不加载任何用户配置」的一部分，且它把结论写到 stdout，不需要 `Write`；强行套 analyze/edit 的 `--restricted` + `--tools` 会改变或削弱它的隔离契约。统一的目标是「同一套 provider 适配层规则（binary、settings、工具面构造、权限规则、失败证据）」，而不是「所有调用共用一个 argv」。edit 的读取面按同一规则构造：提交写入用绝对 `Edit(//<abs>/.harness-evolution/edits.json5)`，工作区读取用目录范围的绝对 `Read(//<abs workspace>/…)` 规则，具体语法在实施步骤 1 的真机取证里定稿，不允许因此放宽到全盘读取。

配套测试与文档：

- 单测：edit argv 断言「无 `--bare`、有 `--safe-mode/--restricted/--strict-mcp-config`、`--tools` 含 `Write`、`--allowed-tools` 是绝对 `Edit(//…)` 规则、`stream-json`、`--max-turns 120`」；工具集缺 `Write` 时的快速失败；非零退出时 detail 含 result 的 `subtype`/`num_turns`。
- 真实 CLI e2e：把 #537 的 opt-in 冒烟扩到 edit 通道（写成功并被 `collect`、越界写入被拒），在部署机以 `HE_AI_AGENT_CLAUDE_E2E=1` 执行。
- 文档：更新 `docs/claude-code.md` 的 edit 工具面/权限说明与验收命令；实现 PR 新增 owning Agent Note 并回填本 issue 的 `adr`。

## 实施步骤

1. 在部署机 CLI 上先取证：同一组新 edit argv 的 `system/init.tools` 是否含 `Write`、`Edit(//<abs>)` 规则能否让 `edits.json5` 写出；把命令与输出贴进 PR。
2. 抽 `_headless_argv()` 与 `_submission_rules()`：`_analyze_argv()` 改为调用同一构造函数，`_edit_argv()` 改成同一形状（去 `--bare`、硬化参数、`stream-json`、绝对路径规则）；把 `EDIT_MAX_TURNS` 从 40 提到 120。
3. 改 `_call()`：非零退出时保留 result 证据；edit 路径接入 `_ensure_submission_tool()` 的快速失败。
4. 补单测与真实 CLI e2e（opt-in，不加 CI workflow）；更新 `docs/claude-code.md` 与 Agent Note。
5. 部署后用一次真实 run 验收：第 6 步 `agent.edit` 为 `ok`，tokens>0，model 非 `unknown`，run 进入 candidate/push/eval。

## 依赖与交付边界

- 依赖：无（#537 的 analyze 修复已在主线，edit 复用它即可）。
- 交付边界：生产代码只改 `apps/api/app/third_party_api/ai_agent/claude_code.py`（`ClaudeCodeProvider` 子类）；测试 `apps/api/tests/**`；文档 `docs/**`、`plans/**`、`.agents/**`。不改 `AIAgentProvider` 基类、`submission.py`、`claude_cli.py`、`Settings`/`config.py`、`deploy/**` 或 workflow。
- 本 issue 只描述实现契约；实现与验证在后续 PR 完成，PR 标题与提交必须含本 issue 编号。

## 独立验证

```sh
pnpm test:api -- tests/test_ai_agent_claude_code.py
pnpm lint:api
pnpm typecheck:api
pnpm verify:flow

HE_AI_AGENT_CLAUDE_E2E=1 \
HE_AI_AGENT_CLAUDE_BIN=/opt/harness/shared/claude-code/current/usr/bin/claude \
  pnpm test:api -- tests/test_ai_agent_claude_code.py -k e2e_real_cli
```

- 单测与静态检查全绿；edit argv 不再出现 `--bare`，`--tools` 含 `Write`，规则是绝对 `Edit(//…)`，`--max-turns` 为 120。
- 单测直接对同一个 `_headless_argv()` 断言 analyze / edit 两个 profile：公共段（硬化参数、`stream-json`、`dontAsk`、`--settings`）只在一处产生，差异段只有 `--tools`、规则、`--max-turns` 与 cwd。
- `EDIT_TIMEOUT_SECONDS` 保持 1800：轮次预算提高后墙钟仍是唯一硬上限，退化会话不会无限延长。
- 真实 CLI e2e：edit 冒烟在 60s 内写出 `.harness-evolution/edits.json5` 并通过 `collect`；越界写入被拒；工具集缺 `Write` 的用例在调用结束时（进程退出后）失败、不重试，且 detail 带 `tools=…`。
- 生产验收：新建一次真实 run，按 `/api/evolution/runs/{id}/events` 检查 `agent.edit`：`outcome=ok`、`inputTokens+outputTokens>0`、`model != "unknown"`、`submissionRounds>=1`；run 进入第 6 步 candidate 并继续 push/eval。

## 验收标准

- 生产 edit 调用能写出并收集 EditPlan；`ai_agent_call` 的 `agent.edit` 为 `outcome=ok`、tokens>0、model 非 `unknown`。
- edit 与 analyze 使用同一套硬化参数与同一种绝对 `Edit(//…)` 提交规则；`--bare` 不再出现在任何 provider argv 里。
- analyze 与 edit 的 argv 都由同一个 `_headless_argv()` 产生；`claude_code.py` 内不存在第二处手拼 `-p` 无头 argv。
- 工具集缺 `Write` 或提交路径被拒时，调用结束时（进程退出后）即判失败并指出缺失工具/被拒路径、不重试，不再以 644s + 一行模型诊断收场。
- 非零退出的 detail 必须带上 CLI result 的结构化证据（`subtype`/`num_turns`/`stop_reason`/`permission_denials`），不再让 stderr 诊断行冒充原因。
- 一次健康的 edit 调用在生产负载下不出现 `error_max_turns`；`ai_agent_call` 记录真实的 `num_turns`，且 120 轮预算下仍以未改动的 `EDIT_TIMEOUT_SECONDS=1800` 为最终上限。
- 权限仍是最小面：Bash、workspace 外写入、未声明工具都被拒；`submission.py` 与基类契约不变。
- 真实 CLI e2e 可在部署机以 opt-in 方式重复执行（不新增 CI workflow）。

## 门禁与 CI

- `pnpm test:api`、`pnpm lint:api`、`pnpm typecheck:api`、`pnpm verify:flow`、`pnpm verify:flow-online`。
- CI lane：`api-static`、`unit-tests-api`、`docs-flow`、`flow-online`；真实 CLI e2e 通过 opt-in 环境变量在部署机执行，不进 CI。

## 非目标

- 不把提交通道换成 `--json-schema` 或其它 Claude Code 专有结构化输出；文件通道必须保留。
- 不放宽权限（不允许全局 `Write`、不允许用 Bash 写提交文件）；不靠调大 `--max-turns` 替代工具面修复。本 issue 按要求把轮次上限从 40 提到 120，但不改 `EDIT_TIMEOUT_SECONDS`。
- 不改 edit prompt、EditPlan 语义、确定性应用器、评测或 UI。
- 不把 `health_check()` 或 `run_skill()` 并进 `_headless_argv()`：前者没有 prompt，后者有沙箱、私有 HOME、固定 session 与 stdout 取结果的独立契约；它们只共用 binary / settings / 失败证据。
- 不改 `AIAgentProvider` 基类、`submission.py` 提交契约、`claude_cli.py` 共享 transport、`Settings`/`config.py` 或部署工作流。
- 不在仓库写入生产凭据、Session 内容或私有数据；不按单个问题新开 milestone。
