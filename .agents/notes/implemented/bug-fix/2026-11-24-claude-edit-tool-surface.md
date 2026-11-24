# Agent Note: Claude Code edit 的提交工具面与统一调用形状

Status: implemented

[English](2026-11-24-claude-edit-tool-surface.en.md) | 中文

## Problem

生产 full run `01M85KA28DRPZ9RN26A3GV5JQ2` 在 patch 阶段阻塞：`agent.edit` 子进程存活约 644 秒后以 `exit_code=1` 退出，`AgentUsage` 全 0、`sessionId=null`、`model=unknown`，`.harness-evolution/edits.json5` 不存在。根因与 #537 修过的 analyze 同源：edit 通道仍带 `--bare`（工具集只有 `Bash`/`Edit`/`Read`，没有 `Write`），且提交规则是相对路径的 `Write(./<relative>)`，而 Claude Code 的文件写只匹配绝对 `Edit(path)`。没有写工具时模型只能反复尝试被 `dontAsk` 拒绝的 `Bash`/`Edit`，直到 `--max-turns 40` 耗尽；provider 又在非零退出时丢弃 stdout result、只报 stderr，于是 `[claude-code:unrecognized_model]` 诊断行冒充了失败原因，644 秒的轮次耗尽形态完全不可见。

## Decision

edit 与 analyze 共用同一个无头调用构造函数 `_headless_argv(_HeadlessProfile)`：binary、`--safe-mode`、`--restricted`、`--strict-mcp-config`、`-p`、`--output-format stream-json --verbose`、`--permission-mode dontAsk`、`--tools`、`--allowed-tools`、`--no-session-persistence`、可选 `--max-turns` 与 `--settings` 只在那一处拼装；`_analyze_argv()` 与 `_edit_argv()` 只装配 profile 差异（prompt、工具集、规则、轮次）。同一份提交规则由 `_submission_rules()` 生成：提交写入统一为绝对 `Edit(//<abs edits.json5>)`；analyze 的读取面是 `Read(//<task>/schema.json)`，edit 的读取面是树范围的 `Read(//<workspace>/**)`。

工具面按阶段固定为常量：`ANALYZE_TOOLS = ("Read", "Write")`，`EDIT_TOOLS = (*READ_ONLY_TOOLS, SUBMISSION_TOOL)` 即 `Read,Grep,Glob,Write`。`Bash` 与 `Edit` 工具始终不在工具面内，edit 的探索只能用只读工具，唯一写入是提交文件。

`EDIT_MAX_TURNS` 从 40 提到 120，`EDIT_TIMEOUT_SECONDS=1800` 不动。40 轮对真实会话偏紧（本次 644 秒 ≈ 40 轮 × 16 秒），120 轮按同一观测约 32 分钟会先撞上 1800s 墙钟，所以墙钟仍是主护栏，轮次上限退化为安全网：健康会话有余量，退化会话最迟在 1800s 被 SIGINT→SIGKILL 收口。

失败证据统一在 `_call()`：非零退出先用 result 的结构化字段（`is_error`/`subtype`/`api_error_status`/`tools`/`stop_reason`/`num_turns`/`permission_denials`）再附有界 stderr；`system/init.tools` 缺 `Write` 在退出 0 与非零两条路径都立即以 `retryable=False` 失败；edit 的 `collect` 失败时把 `permission denied:` 的路径并进 detail，而不是只报 `missing`。

部署机取证（CLI 2.1.325，`/opt/harness/shared/claude-code/current/usr/bin/claude`，服务用户 `harness`）钉住了三个实现前提：`--tools Read,Grep,Glob,Write` 的 `system/init.tools` 返回 `Glob,Grep,Read,Write`（Linux 上确实有 `Grep`/`Glob`）；`Edit(//<abs>)` 规则能写出提交文件，`.harness-evolution/` 目录由 CLI 自动创建；`Read(//<abs workspace>/**)` 树范围只读规则被接受，6 轮、0 denial。`health_check()`（只有 `--version`，没有 prompt）与 `run_skill()`（沙箱、私有 HOME、固定 session、stdout 取结果）保持例外，只共用 `_binary()`、`_settings_file()` 与失败证据归一。

## Alternatives considered

- **给 edit 单独再写一套 argv**：正是这条路径让 edit 在 analyze 修好后仍长期保留 `--bare`；两份 argv 意味着两份会漂移的权限面，放弃。
- **`Write(//<abs edits.json5>)` 规则**：真实 CLI 的文件写权限只认 `Edit(path)`，`Write(path)` 规则不参与匹配；不可行。
- **只提 `--max-turns`**：工具面不可用时轮次再多也写不出提交文件，只会把失败拖到墙钟上限；拒绝。
- **把 `run_skill()` 并进 `_headless_argv()`**：会削掉它的沙箱与 stdout 契约；`health_check()` 没有 prompt，套不进 `-p` 形状；都保持例外。
- **改用 `--json-schema` 原生结构化输出**：把提交绑定到 Claude Code 专有通道，破坏 provider 无关契约；文件通道保留。

## Consequences

- edit 在 CLI 2.1.325 上可写出 `.harness-evolution/edits.json5` 并被 `collect`；opt-in 真实 CLI e2e 覆盖写成功与越界写被拒两个方向，在部署机以 `-k e2e_real_cli` 执行。
- `--bare` 不再出现在 analyze/edit 的任何 argv 里；新增 edit 调用点必须走 `_headless_argv()`，否则单测会看到第二份公共段。
- `stream-json --verbose` 的 stdout 比单 JSON 大，仍只受进程超时与内存约束；失败 detail 不打印模型正文。
- edit 的 120 轮预算只在健康会话里是容量保证；真实成本上限仍是 1800s 墙钟。升级 CLI 时需保持 `--tools`、`Edit(path)` 权限语义与 `--restricted` 等 flag。
