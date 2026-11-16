# Agent Note: 上报绑定的会话来源与 runtime 投影

Status: implemented

[English](2026-11-16-per-report-session-source.en.md) | 中文

## Problem

bad case 上报过去只带 `sessionId`，轨迹补齐完全依赖全局唯一的查询服务；上游契约隐含 Claude Code 形状，`runtime_key` 只能取默认值。多团队接入不同 agent 后，全局 URL 无法按上报路由到正确上游，m9-06 的 parser 工厂也拿不到真实 runtime。若继续在 root-sync 里按 Claude 字段猜来源，runtime 身份会出现第二个 home，新 agent 的接入成本会落到公共遍历与归一化代码上。

## Decision

- 上报新增可选 `sessionSource = {runtime?, sessionUrlTemplate}`。模板必须是 http(s) 绝对 URL、恰好一个 `{sessionId}` 占位符，body 不接受 headers/token；`runtime` 仅作预声明，最终以 envelope 回报为准。
- 定义单接口 envelope：`runtime`、`agentKind`、`parentSessionId`、`childSessionIds`、runtime 专属 `agentMeta` 与规范化 `trajectory` 一次返回。`runtime` 是 parser 与 session-source adapter 共用的唯一词汇表。
- 新增 `third_party_api/session_source/`：`BaseSessionSourceAdapter` 只把 envelope 投影为 runtime 无关的 `SessionInfo`，子类只实现 `parse_agent_meta`；`SessionSourceFactory` 自注册并按 envelope runtime 选择 adapter，未知 runtime 抛 `UnsupportedTraceRuntime`，不回退 Claude。
- root-sync 在首次 claim 时选择来源并固化 `source_kind/source_snapshot`：per-report source 优先，没有则全局源回退；重试复用快照，不因后来上报的新 URL 换源。显式 source 失败即 root 失败，记 `SESSION_SOURCE_*` / `UNSUPPORTED_RUNTIME` 稳定码。
- `runtime_key`、`agent_kind`、`agent_meta` 由 envelope 投影写入 payload；主 agent 可保留 envelope `agentMeta`，subagent 补 `parentAgentId` 并保留上游 `toolUseId`，再由现有 replay 进入 parser 与组树。
- 轨迹规范化从 `HttpSessionQuerySource` 抽到 `session_query/trajectory.py`，两套客户端共享同一套重序列化、重复 key 拒绝与大小/行数上限。

## Alternatives considered

- **用上报的 `runtime` 直接选 adapter 和 parser**：预声明可能错误或缺失，envelope 才是权威；拒绝，改为取到 envelope 后再选 adapter。
- **把 per-report source 只存在 root-sync 状态表**：上报 upsert 是来源的事实 home，状态表只固化“这次 claim 用了哪份快照”；拒绝重复存储上报契约。
- **失败后回退全局源**：会悄悄换掉调用方指定的上游并掩盖配置错误；拒绝，显式 source 失败即 root 失败。
- **在 Claude adapter 里放松 `agentMeta` 为任意 key**：会把 provider 字段泄漏成公共契约并让新 runtime 蒙混过关；拒绝，closed schema 内聚在子类。
- **为每个 root 起独立 HTTP 客户端**：连接与重试策略分散，串行锁也失去进程级语义；拒绝，共享客户端 + 单独串行锁。

## Consequences

- 不带 `sessionSource` 的旧上报行为不变；带 source 的 root 完全绕过全局查询服务，全局服务未配置时也能同步。
- 新增 runtime 仍需同时提供 `session_source/<runtime>.py` 与 `parsers/<runtime>.py`；两者 runtime_key 必须一致，否则 adapter 投影出的 payload 会在 replay 阶段报 `UNSUPPORTED_RUNTIME`。
- 快照要求“重试不换源”，因此上报方修正 URL 后不能靠重报让已失败 root 换源；需要清理状态行或由运维显式处理，这是有意的一致性边界。
- `source_snapshot` 是内部 JSON 契约，没有单独的 OpenAPI；读取侧仍按 closed model 校验，坏快照把 root 标失败而不是静默回退。
- 主 agent 的 `agentMeta` 会进入 payload；它与子 agent 元数据一样必须经过 runtime 专属 closed schema，未知字段会导致整条 envelope 被拒绝。
