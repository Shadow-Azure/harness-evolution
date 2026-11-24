# Claude Code edit 通道工具面统一实现计划（#566）

> **For agentic workers:** this plan follows the superpowers task-by-task style; the linked issue `.agents/flow/issues/bugfix-claude-edit-tool-surface.md` is the implementation contract. Every interactive question is answered from `plans/fullstack-design`, not by asking the user.

**Goal:** 让生产的 `agent.edit` 调用在真实 CLI 上写出 `.harness-evolution/edits.json5` 并通过 `submission.collect`，且 edit 与 analyze 共用同一个无头调用构造函数、同一套绝对权限规则与同一套失败证据。

**Architecture:** `ClaudeCodeProvider` 内部新增唯一的 `-p` 无头 argv 构造函数 `_headless_argv()` 与唯一的提交规则构造函数 `_submission_rules()`；`_analyze_argv()` / `_edit_argv()` 退化为「装配 profile 差异」。edit 去掉 `--bare`，改用与 analyze 相同的 `--safe-mode --restricted --strict-mcp-config --output-format stream-json --verbose --permission-mode dontAsk`，把 `--max-turns` 从 40 提到 120，并用绝对路径 `Read(//<workspace>/**)` 与 `Edit(//<workspace>/.harness-evolution/edits.json5)` 表达读写权限。`_call()` 在非零退出时保留 CLI result 的结构化证据（`is_error` / `subtype` / `api_error_status` / `num_turns` / `stop_reason` / `permission_denials` / `tools`），并在 `system/init.tools` 缺 `Write` 时于调用结束时（进程退出后）以 `retryable=false` 失败。

**Scope:** `apps/api/app/third_party_api/ai_agent/claude_code.py`、`apps/api/tests/**`、`docs/**`、`plans/**`、`.agents/**`。不碰 `AIAgentProvider` 基类、`submission.py`、`claude_cli.py`、`Settings`/`config.py`、`deploy/**` 与 workflow。

**部署机取证（2026-11-24，CLI 2.1.325，`/opt/harness/shared/claude-code/current/usr/bin/claude`，服务用户 `harness`）:**

| 实验 | argv 差异 | `system/init.tools` | 结果 |
---|---|---|---|
| A analyze 形状 | `--tools Read,Write`，规则 `Read(//task/schema.json),Edit(//task/result.json5)` | `Read,Write` | `result.json5` 写出 `{"answer":"ok"}`，`subtype=success`、3 轮 |
| B edit 形状 | 同上，规则 `Read(//ws/README.md),Edit(//ws/.harness-evolution/edits.json5)`、`--max-turns 20` | `Read,Write` | `.harness-evolution/` 目录与 `edits.json5` 一并写出，7 轮、0 denial |
| C 工具面探测 | `--tools Read,Grep,Glob,Write`，规则 `Read(//ws/**),Edit(//ws/.harness-evolution/edits.json5)` | `Glob,Grep,Read,Write` | 三个只读/写工具都在，6 轮、0 denial，`edits.json5` 写出 |

结论：`Edit(//<abs>)` 规则可以写出提交文件，`Read(//<abs>/**)` 整树只读规则被接受，且 2.1.325 在 Linux 上确实提供 `Grep`/`Glob`（与 issue 正文里「Linux 默认集不含这两个」的旧观测相反），因此 edit 的 `--tools` 取 `Read,Grep,Glob,Write` 属于「init 证明存在才加」，不是靠 allowlist 猜；`Bash`/`Edit` 仍不在工具面内。

## 交互问题的设计答案

| 问题 | 答案来源 | 决定 |
|---|---|---|
| edit 的探索面要不要保留 `Grep`/`Glob`？ | [07 §5.5.4](../../fullstack-design/07-backend-implementation.md)「edit 的只读探索」+ 取证 C | 保留；三者都是只读工具，`Bash`/`Edit` 仍被排除 |
| 提交通道是否换成 `--json-schema`？ | [07 §5.5.3](../../fullstack-design/07-backend-implementation.md)「自建字面量通道是默认且唯一路径」 | 不换；文件通道保留 |
| 缺少 `Write` 时是重试还是立即失败？ | [07 §5.5.3](../../fullstack-design/07-backend-implementation.md) 六层防线的第 4 层「不静默降级」+ issue 验收 | 调用结束时（进程退出后）判定失败、`retryable=false`，detail 带 `tools=` |
| `--max-turns` 提到多少？ | issue「实现内容」第 4 点 + 07 §5.5.4 的 `--max-turns` 花费防护 | 120；`EDIT_TIMEOUT_SECONDS=1800` 不动，墙钟仍是主护栏 |
| 是否改 edit prompt / EditPlan 语义？ | issue 非目标 + [07 §5.5.4](../../fullstack-design/07-backend-implementation.md) | 不改；只换 provider 适配层的 argv 与规则 |
| 要不要新增 UI / 对齐原型？ | issue 非目标「不改 UI」 | 不改；冒烟报告只做后端与事件面，不涉及 `harness-evolution.html` 原型 |
| 失败证据是否只报 stderr？ | 07 §5.5.1「归一化返回」+ issue 验收 | 报 result 结构化证据 + 有界 stderr，不打印模型正文 |

### Task 1: 统一无头调用形状

**Files:** Modify `apps/api/app/third_party_api/ai_agent/claude_code.py`.

- [x] 新增 `_HeadlessProfile`（prompt、tools、rules、可选 `max_turns`）与 `_headless_argv(profile, settings_file)`，独占 binary、硬化参数、`-p`、`stream-json --verbose`、`dontAsk`、`--tools`、`--allowed-tools`、`--no-session-persistence`、可选 `--max-turns`/`--settings`。
- [x] 新增 `_submission_rules(*, directory, result_path, read_tree)`：提交写入统一为 `Edit(//<abs result>)`；analyze 的读取面是 `Read(//<task>/schema.json)`，edit 的读取面是 `Read(//<workspace>/**)`。
- [x] `_analyze_argv()` / `_edit_argv()` 只装配 profile，不再各自拼公共段。
- [x] `EDIT_MAX_TURNS` 40 → 120；新增 `EDIT_TOOLS = ("Read", "Grep", "Glob", "Write")` 并保留 `ANALYZE_TOOLS`。

### Task 2: 失败证据与快速失败

**Files:** Modify `claude_code.py`; extend `apps/api/tests/test_ai_agent_claude_code.py`.

- [x] `_call()` 非零退出时改用 `_failure_detail(result, parsed)`：`exit_code`、`is_error`、`subtype`、`api_error_status`、`tools`、`stop_reason`、`num_turns`、`permission_denials`，再拼有界 stderr。
- [x] `parsed.tools` 存在但缺 `Write` 时抛 `retryable=false` 的专用错误，detail 带 `tools=`，并在 edit 成功路径上同样调用 `_ensure_submission_tool`。
- [x] edit 的 `collect` 失败且 result 携带写权限 denial 时，detail 指出被拒路径，而不是只报 `missing`。

### Task 3: 单元测试与真实 CLI e2e

**Files:** `apps/api/tests/test_ai_agent_claude_code.py`.

- [x] edit argv 断言：无 `--bare`、四个硬化参数、`stream-json`、`--tools` 含 `Write`、规则为 `Read(//<ws>/**)` + `Edit(//<abs edits.json5>)`、`--max-turns 120`。
- [x] 同一个 `_headless_argv()` 产出 analyze/edit 两个 profile：公共段只在构造函数里出现，差异段只有 tools、rules、`--max-turns` 与 cwd。
- [x] 缺 `Write`（非零退出与退出 0 两种）都在调用结束时（进程退出后）判定失败、不重试，且 detail 带 `tools=`；非零退出 detail 含 `subtype`/`num_turns`。
- [x] 真实 CLI e2e 扩到 edit 通道：写成功并被 `collect`、越界写入被拒；仍由 `HE_AI_AGENT_CLAUDE_E2E=1` 开关控制，不进 CI。

### Task 4: 文档与决策记录

**Files:** Modify `docs/claude-code.md`（+ `.en.md`，跑 `pnpm record:i18n`）; create `.agents/notes/implemented/bug-fix/2026-11-24-claude-edit-tool-surface.md`（+ `.en.md` + `.i18n.yaml`）; update the flow issue（`status`、`adr`）。

- [x] 文档写清 edit 的工具面、绝对规则、失败证据与验收命令，中英成对。
- [x] Agent Note 记录「同一构造函数 + 绝对 Edit 规则 + 轮次预算」的取舍与 2.1.325 取证。
- [x] flow issue 状态 `ready → in-progress`，`adr` 指向新 Note。

### Task 5: 验证

- [x] `pnpm test:api -- tests/test_ai_agent_claude_code.py`（Windows 本机 44 passed / 4 skipped；2 个 POSIX-only runner 用例在 `main` 上同样失败，以 CI 为准）
- [x] `pnpm lint:api`、`pnpm typecheck:api`、`pnpm verify:flow`、`pnpm test:gates`（lint 绿、`mypy --platform linux` 457 文件零问题、flow 绿；`test:gates` 在 Windows 上 `spawn pnpm ENOENT`，由 CI 复核）
- [x] 部署机 opt-in e2e（`HE_AI_AGENT_CLAUDE_E2E=1` + `HE_AI_AGENT_CLAUDE_BIN`）通过（2026-11-24 在 `8.149.232.63` 用生产 CLI 2.1.325 实跑 `edit_workspace`：plan 被 `collect`、4856/1103 tokens、工作区未改）
- [ ] 合并部署后一次真实 run 的第 6 步 `agent.edit` 为 `ok`、tokens>0、model 非 `unknown`
