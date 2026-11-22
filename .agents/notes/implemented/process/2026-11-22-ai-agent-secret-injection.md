# Agent Note: AI Agent 三配置经 GitHub Secrets 注入 .env

Status: implemented

[English](2026-11-22-ai-agent-secret-injection.en.md) | 中文

## Problem

自进化的模型审查与 patch 生成依赖 `AI_AGENT_PROVIDER`、`HE_AI_AGENT_CLAUDE_BIN`、`HE_PATCH_SOURCE_MODE` 三个运行配置，生产值必须由部署管道写入服务器 `/opt/harness/shared/.env`。`inject-config.py` 的既有语义是「输入里没有的键保留服务器旧值」——删除 Secret 后旧值继续生效，例如从 `agent-edit` 切回 `placeholder` 时残留值仍指向 `agent-edit`。因此「配置的唯一来源是 Secrets」要求缺失本身成为一种显式状态。

## Decision

三个 Secret 与键同名：存在且非空时，deploy 步骤把 `KEY base64(值)` 追加进 `ENTRIES`，经既有 base64 + stdin 通道交给 `inject-config.py`；缺失或为空时，把 `--unset KEY` 追加进 `UNSET_ARGS`。三键的写入与移除因此和代理/token 的条件 unset 走同一套机制，日志只报已写入计数与其余已移除，不出现值。`HE_PATCH_SOURCE_MODE=agent-edit` 不在本 issue 扩展：当前 Settings 只接受 `placeholder` / `minimal-config`，在 #488（bugfix-21）落地前写入 `agent-edit` 会让服务启动校验失败。

## Alternatives considered

改用 GitHub Variables：三键并非敏感值，但会引入第二条配置通道，且 Variables 在 fork PR 与环境覆盖上的可见性和优先级不同，违背「Secrets 单一来源」的既定边界。改用 workflow_dispatch inputs：只有手动触发才有输入，push main 的自动发布没有，行为随触发方式漂移。让 `inject-config.py` 在缺行时删除：会改变脚本对任意调用方的语义，且无法区分「本次没打算注入」与「Secret 被删除」；显式 `--unset` 把意图留在 workflow 层。把三键写死在 env 模板里：仓库不存生产值，模板只做示例与默认值说明。

## Consequences

每次发布都会显式设置或移除三键，服务器 `.env` 与 Secrets 保持同构；删除 Secret 后重启即回退 Settings 默认值（`claude-code` / `~/.local/bin/claude` / `placeholder`）。workflow 在组装前拒绝含换行/回车的三键值并中止发布：跳过不是删除，旧值不会因解码跳过而保留；其余键解码失败仍告警跳过。注入通道不校验枚举，非法值仍由服务启动校验拦截；回退默认值不保证在 `harness` 下可用——CLI 的 settings 与凭据须对该用户可读，稳定路径与共享 settings 归 bugfix-17/M15。`agent-edit` 的可用性取决于 #488。新增同源配置项时沿用「存在写入 / 缺失 unset」模式，避免陈旧键长期生效。
