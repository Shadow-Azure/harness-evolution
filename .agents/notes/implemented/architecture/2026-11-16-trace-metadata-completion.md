# Agent Note: 真实元数据兼容、完成状态与定义证据解析

Status: implemented

[English](2026-11-16-trace-metadata-completion.en.md) | 中文

## Problem

真实 Claude Code 会话的 `meta.json` 出现了 `isBuiltIn`、`pickedEffortModel`、`finished` 等新字段，子 Agent JSONL 还会注入 `prompt_snapshot`、`api-request-shape`、Skill body 与 `toolUseResult`。旧的封闭元数据校验会把整份 Session 判为不可导入；解析器也只能看到文本与工具计数，无法表达“根停在未返回的 tool_use”“子 Agent 没有 `end_turn`”“任务快照仍有未完成项”，更拿不到 Agent、Skill 定义与文件读取的稳定指纹。解析健康 `status` 被迫同时承担执行完成度，真实故障会被普通工具错误掩盖。

## Decision

- 元数据校验改为“已知字段严格、未知字段降级”：`agentType`、`description`、`spawnDepth`、`model` 等已知字段继续按类型与列长校验；未知标量经去控制字符、长度截断后进入 `agents.meta`，未知对象/数组丢弃，并产生稳定 `UNKNOWN_AGENT_METADATA` 警告。`isBuiltIn`、`pickedEffortModel`、`finished` 提升为已知字段。
- 执行完成度只从显式证据推导：assistant `message.stop_reason` 为 `end_turn` 记 `completed/end_turn`；为 `tool_use` 且仍有未配对调用记 `interrupted/tool_use_open`，无未配对调用记 `interrupted/missing_report`；`interrupted` 类停止原因记 `external_interrupted`；API 错误消息记 `failed/external_failed`。没有 `stop_reason` 的旧载荷保持 `legacy_unknown`，不从“最后一条是 assistant”猜测完成。
- 稳定诊断码 `TOOL_USE_OPEN`、`MISSING_FINAL_REPORT`、`TASK_SNAPSHOT_PENDING` 只在对应用显式证据存在时产生；任务快照从 `task_reminder` 或 `toolUseResult.task` 的 pending/in-progress 计数读取，不保存任务文本。
- Agent 定义从 `prompt_snapshot.systemPrompt[0]` 或 `api-request-shape.system` 提取；通用权限提示、Notes、token budget 段落在 hash 前剥离。`isBuiltIn` 为真时只记 `definition_source=builtin`，不产生 body hash。
- Skill body 从 `isMeta + sourceToolUseID` 注入提取，保存 path 与归一化 body hash；文件读取从 Read/Edit 的 `toolUseResult` 提取 path、1-based range、complete 与内容 hash，Bash 仅在其结果携带文件身份时记录。证据结构只含 hash、路径、范围与来源，不保留正文。
- 解析结果通过既有证据列落库：`session_families`/`agents` 写执行完成度，`agents` 写 Agent 定义 hash 与来源，Skill 事件写 `definition_hash`。文件读取的 path/range 暂无列，保留在 parser 证据结构；对象 revision、触发坐标、关系置信度与知识事件列分别归 M9-03/M9-04/M9-05。
- 会话级执行完成度按“任一 failed → failed；任一 interrupted → interrupted；任一 legacy_unknown → legacy_unknown；否则 completed”聚合，workflow 合成节点不参与；`end_reason` 优先主 Agent 的原因。
- `ClaudeCodeTraceParser.parser_version` 升到 2，使存量 claude-code 载荷在下次同步/重放时补齐新证据；其他 runtime 不受影响。
- 请求模型与实际上报模型继续分列：`requested_model` 取 `meta.model`/`pickedEffortModel`，`reported_model` 取 assistant 实际 model；两者都是具体模型标识且不一致时产生 `MODEL_EVIDENCE_CONFLICT`，不互相覆盖。

## Alternatives considered

- **继续封闭元数据并逐个加入新字段**：下一次 provider 漂移仍会整树拒绝，违背“漂移不丢树”的目标。
- **用 `ended_with_assistant` 推断完成**：旧载荷会被误标为 completed，把“未知”变成“已完成”，破坏证据语义。
- **把定义与文件正文写入数据库**：正文属于 provider 私有内容，且会放大隐私与存储风险；只保留 hash/路径/来源。
- **现在给 agent_events 增加 path/range 列**：06 设计把知识文档的 `source_path` 留给 M9-05；本轮先把路径与范围留在 parser 证据结构，避免提前固化查询口径。
- **把 parser_version 升级推迟到 M9-04**：会让新证据在 M9-02 上线后只覆盖新载荷，存量真实会话继续 `legacy_unknown`；解析语义变化应当触发本 runtime 重放。
- **把 Bash 输出一律当文件读取**：Bash 结果没有可靠文件身份，凭空猜路径会制造假证据；只在结果显式携带文件结构时记录。

## Consequences

- 文件读取的 path/range 目前只在 parser 证据结构中存在，API/数据库尚不可查询；M9-05 需要知识事件列时再接。
- 旧载荷只要没有显式 `stop_reason` 就保持 `legacy_unknown`，客户端必须把它当“未知”而不是“已完成”。
- claude-code 的 parser_version 从 1 升到 2，部署后首次同步会重放该 runtime 的存量 source_records；这是预期成本。
- `agents.meta` 现在可能包含截断后的未知标量字段；字段名会进入 `UNKNOWN_AGENT_METADATA` 警告，但值不会进入日志或 API。
- 会话级 `execution_outcome` 与解析健康 `status` 仍是两条独立轴，UI 和归因读取时需要显式选择。
- 关系分级、对象 revision、触发坐标与知识文档仍分别由 M9-03、M9-04、M9-05 完成；本 Note 不承诺它们已经可用。
