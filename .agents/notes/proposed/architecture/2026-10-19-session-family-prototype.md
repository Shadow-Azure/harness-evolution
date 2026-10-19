# Agent Note: Session 家族原型与跨 Agent 分析

Status: proposed

[English](2026-10-19-session-family-prototype.en.md) | 中文

## Problem

Codex 的 subagent 会写入独立 rollout，但主会话才是用户发起分析的单位。若把一个 rollout 当作完整 session，主 agent 的诊断会漏掉子 agent 的执行、skill 使用与失败证据；若简单拼接文本，又会丢失父子关系、agent 路径和稳定锚点。

## Decision

- Session family 成为一等分析范围：主 rollout 加全部后代 subagent，按 `source.subagent.thread_spawn.parent_thread_id` 递归组装。
- rollout 文件身份是主键；`session_id` 不能在子 agent 中作为唯一键，因为子 rollout 可能复用父会话的 `session_id`。
- M1 使用 4 个真实主会话家族作为原型样本，共 64 个 rollout、25,170 条记录、约 72.2MB，最大深度 4。
- M1 先做本地快照适配层与前端体验，不接 SQLite 与 API；原始 JSONL 不进入仓库。
- 问题分析先逐 agent 提炼证据，再由主 agent 合并、去重并形成跨 agent 结论；证据保留 rollout、agent 路径、行号与 item/call id。
- M1 的问题、归因与自进化数据全部打桩；验证平台通过接口契约模拟，不执行真实改动。
- 演示链路固定为“Session 搜索 → 执行流 → 问题 → 归因解释 → 自进化模拟 → 验证指标 → 接纳/拒绝”。
- 主 agent 与全部子 agent 共用一张执行流程图；节点承载状态、问题数与证据入口。
- 主 agent 与全部子 agent 的问题共用一份家族级列表，以来源标签区分而不是拆成独立视图。
- 每条归因必须指定目标类型与目标 ID（skill 或 agent），自进化按该目标聚合问题进行模拟训练/改进。
- M1 的“训练”是 harness 层改进模拟，不做模型权重训练。

## M1 快照契约落地

- 索引层只读取每个 rollout 的首条 `session_meta`；正文按 thread 懒加载，原始 JSONL 不进入仓库。
- `threadId`（`payload.id`）是 agent 主键，`rolloutId`（相对路径）区分 segment，`sessionId` 只作展示字段。
- 同一 thread 的续段挂在同一 `AgentNode` 下；主段记录数与续段记录数分开报告。
- guardian review thread 不进入 Session Family；文件仍保留在原始目录，需要时可单独读取。
- 时间线以 `TimelineItem` 为稳定 envelope，保留 command、file-change、mcp、collab、subagent 与 token 等 item；`event_msg.item_completed` 与 `response_item` 按 id/call_id 去重。
- 浏览器读取路径不在 #10 范围；#14/#15 决定快照如何进入前端。

## Alternatives considered

- 把每个 subagent 当作独立 session：实现简单，但无法回答主任务为何失败；否。
- 把全部 rollout 拼成一条时间线：会丢失 agent 归属，且重复 ID 与调用关系难以还原；否。
- 用 `session_id` 作为唯一键：子 rollout 已出现复用父会话 ID 的情况，会覆盖数据；否。
- 原型直接接 SQLite 与 API：反馈更慢，且会把视觉验证与数据管线耦合；否。

## Consequences

- 快照加载器必须递归建立家族索引并懒加载单个 rollout。
- 时间线需要虚拟化、按 agent 过滤，并提供父子 agent 导航。
- SQLite 需要保存 parent rollout、depth 与 agent path，分析任务以 root rollout 为入口。
- 跨 agent 结论必须去重，并允许从主问题展开到各个相关子 agent 的证据。
- 原型必须显式标注打桩数据，并把模拟验证与真实平台调用区分开。
- 执行流程图与归因目标必须共用稳定 ID，保证从子 agent 问题到目标聚合不会断裂。
