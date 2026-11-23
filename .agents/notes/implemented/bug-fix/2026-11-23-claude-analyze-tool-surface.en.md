# Agent Note: Claude Code analyze submission tool surface and write permissions

Status: implemented

English | [中文](2026-11-23-claude-analyze-tool-surface.md)

## Problem

A production `cluster.review` analyze call under `--bare` could not see `Write`: bare narrows the tool set to `Bash`/`Edit`/`Read`, while the submission channel requires the model to write `result.json5` into the task directory; `--allowed-tools` is only an allow list and cannot add a tool that does not exist. The model could only try `Bash`/`Edit` (denied by `dontAsk`) or stop, so the submission file was necessarily missing. The one feedback retry after the first failure faced the same tool surface and eventually hit the 300s `ANALYZE_TIMEOUT_SECONDS`, normalized as `cancelled`.

Two independent gaps existed beyond the tool surface. The submission allow rule used a relative path, `Write(./result.json5)`, while Claude Code checks file permissions against the path of the actual call. More importantly, the current CLI checks file writes against `Edit(path)` rules; `Write(path)` rules do not participate in file-permission matching. Removing `--bare` alone would therefore still deny `Write(./result.json5)`.

## Decision

The analyze argv drops `--bare` and always passes `--safe-mode`, `--restricted`, and `--strict-mcp-config` to keep bare's context minimization (no `CLAUDE.md` auto-discovery, no hooks/plugins/MCP, no command-running tools), plus `--tools Read,Write` to reduce the built-in set to reading the schema and writing the submission file. `--permission-mode dontAsk` is unchanged.

Tool rules use the absolute task directory: `Read(//<task>/schema.json)` and `Edit(//<task>/result.json5)`. The task directory is resolved before building argv and is also the CLI `cwd`, so a symlinked temp root cannot make the requested path and rule path disagree. Only the single `Edit(//<task>/result.json5)` write is allowed; `Bash`, the `Edit` tool, and writes outside the task directory stay denied.

Analyze switches to `--output-format stream-json --verbose` to read the CLI's real tool list from `system/init` and `permission_denials`, `stop_reason`, and `num_turns` from the result. A tool set without `Write` or a denied submission path raises `AgentProviderError` immediately instead of spending the feedback retry; a timeout/cancellation detail keeps bounded stderr and that structured evidence. The edit channel is outside this issue's contract and its argv is unchanged.

## Alternatives considered

- **`--bare --tools Read,Write`**: on 2.1.323 init returned only `Read`; `Write` is not added back, so this is not viable.
- **Pre-create an empty `result.json5` and allow `Bash`/`Edit`**: needs an extra tool or a command surface, and `Edit`'s create semantics under `--bare` were not verified; rejected.
- **`Write(//<task>/result.json5)` rule**: the real CLI still denies the write; file-write permission is governed only by `Edit(path)`.
- **Native `--json-schema` structured output**: binds submission to a Claude Code-specific channel and breaks the provider-neutral contract; the file channel stays.
- **Allow global `Write` or Bash file writes**: widens the service permission surface and violates least privilege; rejected.

## Consequences

- Analyze can actually write and collect `result.json5` on CLI 2.1.323; the local real-CLI e2e covers both the successful write and a denied out-of-bounds write.
- `--restricted`, `--safe-mode`, `--strict-mcp-config`, and `--tools` are existing 2.1.323 flags, so no deployment configuration is added; a CLI upgrade must preserve these flags and the `Edit(path)` permission semantics.
- `stream-json --verbose` produces more stdout than the single-JSON format; the process timeout and memory remain the only bounds, and the provider never prints model prose.
- The edit channel keeps its existing argv; an enabled agent-edit path still needs its own tool-surface verification.
