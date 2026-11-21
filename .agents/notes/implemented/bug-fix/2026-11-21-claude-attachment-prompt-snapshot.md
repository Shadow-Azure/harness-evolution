# Agent Note: Claude Code attachment 嵌套 prompt snapshot

Status: implemented

[English](2026-11-21-claude-attachment-prompt-snapshot.en.md) | 中文

## Problem

Claude Code 子 agent 的定义证据在设计文档和解析器里一直被描述为顶层的 `prompt_snapshot.systemPrompt[0]`（或 `api-request-shape.system`）。2026-11-21 对生产 `sessionUrlTemplate` 的实测显示，真实形状是 `type=attachment`、`attachment.type=prompt_snapshot`、`attachment.systemPrompt[0]`：没有顶层 `type=prompt_snapshot` 记录，`agentMeta` 也只有 `name`。解析器只检查顶层 `type=prompt_snapshot` / `api-request-shape`，因此所有 agent 事件都没有 `definition_hash`，agent 目标无法关联。

实测的 6 个子 agent 中，`attachment.systemPrompt[0]` 的 SHA-256 与镜像 a7ec200 的 `AGENT.md` 完全一致（code-generator `c816a39e…`、spec-reviewer `86b6567b…`、code-quality-reviewer `3742e03f…`），说明数据存在，缺口在解析器的形状识别。

还有第二个阻断：子 agent 的 `agentMeta` 只有 `name`、没有 `agentType`，而 `_agent_revision` 依赖 `agentType`，即使 attachment 修复产出 body hash，`agent_revision` 仍为 None；`_apply_agent_revisions` 只在 revision 非空时把 child 的 `definition_hash` 挂到父 `kind=agent` 事件，所以父事件仍是 `unknown`，matcher 仍匹配不到。

## Decision

- Claude Code 的 `prompt_snapshot` 有两种等价形状：顶层 `type=prompt_snapshot` + `systemPrompt`，以及 `type=attachment` + `attachment.type=prompt_snapshot` + `attachment.systemPrompt`。
- 解析器优先读取 `prompt_snapshot`（两种形状等价）；`definition_source` 仍记为 `prompt_snapshot`，不新增枚举值。
- `api-request-shape.system` 保留为兼容兜底；实际数据的 `api-request-shape.shape.system` 是运行时 system 快照，hash 与目标 `AGENT.md` 不一致，不能覆盖 `prompt_snapshot`，也不作为本切片的定义来源。
- 该变更还必须在 `agent_tree._apply_agent_revisions` 中，即使 child revision 为 None，只要 `agent_definition_hash` 存在，也把 `definition_hash` 挂到父 `kind=agent` 事件；matcher 使用 `definition_hash` 命中 body hash，不改变 `agent_revision` 的 `agentType + isBuiltIn + body hash` 语义。
- 因此这不是纯 Claude 子类修复：需要 `apps/api/app/service/acquisition/agent_tree.py` 的一处基类传播改动；`parser_version` 升级触发已存 payload 重放，仍无需数据库/契约/matcher 改动。
- 设计文档 [07 §2.3](../../../../plans/fullstack-design/07-backend-implementation.md#23-归一化行数组--中间结构) 与 [15 §9.2](../../../../plans/fullstack-design/15-v1-v2-gap-analysis.md#92-对象-revision-与模型身份) 已同步这一事实。

## Alternatives considered

- **只消费 `agentMeta.promptSnapshot`**：生产 `agentMeta` 只有 `name`，没有 `promptSnapshot`；该路径不能解释实测数据，也不能让 6 个 agent 命中。
- **只按 agent 名称匹配**：同名定义可能跨版本变化，会把错误版本归因到当前 target；身份必须是 body hash。
- **把 `api-request-shape.shape.system` 当定义正文**：实测 hash 与目标 `AGENT.md` 不一致；用它会产生错误 identity。
- **拆整包 root content 按 `agentId` 切分**：本次数据是 per-agent envelope，不需要切分；该方案会把问题扩大到会话模型。

## Consequences

- issue [#471](https://github.com/Shadow-Azure/harness-evolution/issues/471) 记录并跟踪 parser 子类修复与 `agent_tree` 的 `definition_hash` 传播；本 PR 已实现两处，父 `kind=agent` 事件即使没有 target revision，也携带 body hash。
- 不改变现有顶层 `prompt_snapshot` / `api-request-shape.system` 的兼容行为；不把 `shape.system` 升级为定义来源。
