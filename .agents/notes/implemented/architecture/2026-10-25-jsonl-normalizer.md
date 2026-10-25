# Agent Note: JSONL 归一化边界

Status: implemented

[English](2026-10-25-jsonl-normalizer.en.md) | 中文

## Problem

Claude Code 原始 JSONL 同时包含用户输入、assistant 分片、工具调用、工具结果、隐藏思考、usage 与 provider 控制记录。若把这些内容直接落表，会重复存储大段消息、暴露内部推理，并让统计口径随流式分片漂移。

## Decision

单 payload 归一化是纯函数，parser version 从 `1` 开始。坏行及合法 JSON 的非对象记录独立生成稳定、脱敏的 issue，不中断后续行。assistant 以 `message.id` 去重消息数，同一消息的多条流式记录以最后观测的累计 usage 为准，token 只取 input/output 两项；工具调用只统计 `tool_use` 并保留 `tool_use_id` 关联，真实数据中的 `server_tool_use` 不计入当前 `tools_count`；错误统计所有 `is_error=true` 内容块。模型取出现次数最多的非空 assistant model，平票按首次出现决定，同时保留全部模型供后续会话聚合。

只有主 Agent 的字符串/文本数组用户输入，以及 `type=attachment` 记录中的 `origin.kind=human` 或兼容的 `queued_command.origin.kind=human` 形状生成用户轮次；meta、tool result、四类控制消息、其他 origin 以及仅携带 attachment 外观的控制记录不生成。有效用户轮次必须具有合法时间戳；缺失时生成稳定脱敏 issue 并跳过该轮，避免产生无法写入非空时间列的数据。Skill、Agent、Workflow 工具调用生成事件，保留触发工具 id、名称、描述、从 1 开始的行号和从 0 开始的唯一 assistant 消息偏移。解析结果保留递归冻结的原始 `agent_meta` 副本供树组装使用；用户轮次之外的结构化 block 身份单独保留，消息、thinking、工具结果文本只存在于解析过程中，不进入公开结果或持久化字段。

归一化在 m2-03 只产出统计与锚点；Agent 树组装、业务表重写和 `source_records.processed_*` 更新分别留给 m2-04 与 m2-05。解析 issue 通过 repository 追加到指定 `sync_runs.errors`，只保存 session/agent/line/code/message。

## Alternatives considered

- 把完整消息与内容块落表：违背设计的时间线裁撤决定，并放大隐私与存储面积。
- 固定使用流式 assistant 首片的 usage：真实流式记录常在后续分片补上累计值，会把整条消息的 token 少计到 0 或不完整值。
- 将 `server_tool_use` 合并进工具总数：当前权威设计只定义 `tool_use`，改变口径需要单独设计评审。
- 缺少合法行身份时丢弃整个文件：会扩大单条 provider 异常的损失，不符合坏行隔离目标。

## Consequences

fixture manifest 现在是 normalizer 的 golden oracle，payload 必须能复现声明的事件和统计；伪造声明由测试拦截。后续 M2 必须以同一 parser 和 version 生成树、更新处理游标，并在升级派生语义时递增 `CURRENT_PARSER_VERSION`。provider 新增工具或消息形状时先补兼容测试和设计记录，不能静默改变统计。
