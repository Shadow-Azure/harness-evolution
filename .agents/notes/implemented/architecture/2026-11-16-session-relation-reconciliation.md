# Agent Note: Session 父子关系重建与未解析分支

Status: implemented

[English](2026-11-16-session-relation-reconciliation.en.md) | 中文

## Problem

M9-01/M9-02 已经能解析真实元数据、tool result 与执行完成度，但会话树仍只有“能连上/连不上”的二元关系：父 `Agent` tool_use 与子 metadata 的 `toolUseId` 一致却缺少 tool result 时，真实导出会被误判为 unlinked；只有 `parentAgentId` 弱证据时，节点会被悄悄挂到主 Agent；没有任何父工具身份时，节点虽然临时保留，却没有稳定的关系证据可供 API 和 UI 展示。归因与后续 run 因此无法区分“强证据关联”“缺结果降级”“弱证据合成”和“完全未解析”。

## Decision

- 关系分级只在树装配阶段计算：`authoritative` 要求父 `Agent` tool_use、父转录中对应的 tool result、子 metadata 的 `toolUseId` 三者一致；只有 tool_use 与 metadata 一致而父转录缺少 result 时为 `derived`。
- 只有 `parentAgentId` 弱证据时生成 `synthetic` 关系，并在父节点补一条确定性的合成 `agent` 触发事件；完全没有可用父身份时生成 `unresolved` 关系，仍挂到主 Agent 并保留 `MISSING_PARENT_TOOL_USE_ID` / `UNKNOWN_PARENT_TOOL_USE_ID` / `AMBIGUOUS_PARENT_TOOL_USE_ID` 诊断，节点不从树中消失。
- 关系置信度写入父节点的 `agent_events.relation_confidence`，与 [06 §3.4](../../../../plans/fullstack-design/06-database-design.md) 的列语义一致；`ParsedEvent` 只增加一个可选字段，解析器本身不判断父子关系。
- `derived` 子 Agent 仍按原顺序挂入树，并保留自己的执行完成度；前端在节点上显示关系证据标签，`derived` 或缺最终报告时显示“未返回最终报告”。
- `ClaudeCodeTraceParser.parser_version` 从 2 升到 3，让存量 `claude-code` 载荷在下次同步/重放时重新装配并写入关系列；关系分级是装配语义变化，不升级会让旧会话永久停留在 NULL。
- 03/05/06 的 DTO、数据库列和前端字段本已存在，本 Note 只补写入方与展示，不新增表或重复字段。

## Alternatives considered

- **继续用 linked/unlinked 二元状态**：无法表达“tool_use 一致但缺 result”的真实降级路径，也无法为 UI 提供稳定证据；拒绝。
- **把关系置信度放到 `agents` 行**：06 已把 `relation_confidence` 定义在触发事件上，一个 Agent 可能由多条触发点解释；新增节点列会产生两个真相；拒绝。
- **缺 result 就断开节点**：会把真实导出中的子 Agent 静默丢掉，违背“未解析节点不会消失”；拒绝。
- **让前端按 toolUseId 自己猜关系**：前端无法看到父转录的 tool result，猜测结果与导出/内部树不一致；关系必须由装配层统一计算；拒绝。
- **不升 parser_version，靠手工重放**：存量真实会话不会自动获得关系证据，验收只覆盖新导入；升级版本是仓库既有的证据回填机制；拒绝。

## Consequences

- 存量 `claude-code` 载荷会在部署后首次同步时重放一次，成本与 M9-02 的版本升级相同。
- 弱证据与未解析节点会在父节点触发链末尾多出一条合成事件；这是为了让节点在树和 UI 中可见，而不是伪造真实 provider 事件。
- `unresolved` 节点在结构上仍挂到主 Agent，但关系证据明确为未解析；调用方应以 `relationConfidence` 而不是父链接是否存在来判断证据强度。
- 前端节点新增关系标签与完成警告；`authoritative` 之外的标签使用状态色，关系为空的历史会话不显示标签。
- 潜在匹配、按开始时间猜父级和隐藏未解析节点仍不在本切片内。
- 关系分级覆盖 Agent tool 触发的子 Agent；forked skill、workflow-subagent 与 in-process teammate 的边不是父 Agent tool 调用，`relation_confidence` 保持 NULL，不能据此区分“未重放”与“从未分类”。
