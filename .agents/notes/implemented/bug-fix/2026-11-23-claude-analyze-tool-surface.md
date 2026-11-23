# Agent Note: Claude Code analyze 的提交工具面与写权限

Status: implemented

[English](2026-11-23-claude-analyze-tool-surface.en.md) | 中文

## Problem

生产 `cluster.review` 的 analyze 调用在 `--bare` 下看不到 `Write`：bare 把工具集收窄为 `Bash`/`Edit`/`Read`，而提交通道要求模型写任务目录的 `result.json5`；`--allowed-tools` 只是允许列表，不能把不存在的工具加回来。模型只能尝试被 `dontAsk` 拒绝的 `Bash`/`Edit` 或直接结束，提交文件必然缺失；首次失败后的反馈重试继续面对同一工具面，最终撞上 300s `ANALYZE_TIMEOUT_SECONDS`，被归一为 `cancelled`。

工具面之外还有两个独立缺口：提交通道的 allow 规则写成相对路径 `Write(./result.json5)`，而 Claude Code 的文件权限按本次调用的实际路径匹配；更关键的是，当前 CLI 的文件写检查使用 `Edit(path)` 规则，`Write(path)` 规则不参与文件权限匹配。因此即使去掉 `--bare`，`Write(./result.json5)` 仍会被拒绝。

## Decision

analyze 的 argv 去掉 `--bare`，固定传 `--safe-mode`、`--restricted`、`--strict-mcp-config` 保留 bare 的上下文最小化（不自动发现 `CLAUDE.md`、忽略用户/项目 settings 的 hooks/plugins、关闭 MCP、不提供命令执行工具），再用 `--tools Read,Write` 把内置工具收缩为读取 schema 与写提交文件两项；`--permission-mode dontAsk` 不变。

工具规则由本次任务目录的绝对路径构造：`Read(//<task>/schema.json)` 与 `Edit(//<task>/result.json5)`。任务目录在构造 argv 前解析为真实路径，并同时作为 CLI 的 `cwd`，避免临时根目录是软链时请求路径与规则路径不一致。写入只放开 `Edit(//<task>/result.json5)` 这一条；`Bash`、`Edit` 工具与任务目录外的写入仍被拒绝。

analyze 改用 `--output-format stream-json --verbose`，从 `system/init` 读取 CLI 真实工具列表，从 result 读取 `permission_denials`、`stop_reason` 与 `num_turns`。工具集缺少 `Write` 或提交路径被拒时立即抛 `AgentProviderError`，不再消耗反馈重试；超时/取消的 detail 保留有界 stderr 与上述结构化证据。edit 通道不在本 issue 的契约内，argv 保持原样。

## Alternatives considered

- **`--bare --tools Read,Write`**：在 2.1.323 上 init 只返回 `Read`，`Write` 不会被加回；不可行。
- **预创建空 `result.json5` + `Bash`/`Edit`**：需要额外工具或命令执行面，且 `--bare` 下 `Edit` 的创建语义未验证；放弃。
- **`Write(//<task>/result.json5)` 规则**：真实 CLI 仍拒绝写；文件写权限只认 `Edit(path)`。
- **`--json-schema` 原生结构化输出**：会把提交绑定到 Claude Code 专有通道，破坏 provider 无关契约；继续保留文件通道。
- **全局放开 `Write` 或允许 Bash 写文件**：扩大服务权限面，违背最小权限；拒绝。

## Consequences

- analyze 在 CLI 2.1.323 上可真正写出 `result.json5` 并被 collect；本地真实 CLI e2e 覆盖写成功与越界写被拒两个方向。
- `--restricted`、`--safe-mode`、`--strict-mcp-config` 与 `--tools` 是 2.1.323 已有 flag，不新增部署配置；升级 CLI 时需保持这些 flag 与 `Edit(path)` 权限语义。
- `stream-json --verbose` 的 stdout 比单 JSON 大，仍只由进程超时与内存约束；provider 不打印模型正文。
- edit 通道沿用既有 argv，agent-edit 若启用仍需单独验证其工具面。
