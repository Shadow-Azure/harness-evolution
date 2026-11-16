# Agent Note: 多 runtime parser 工厂与 runtime 身份

Status: implemented

[English](2026-11-16-multi-runtime-parser-factory.en.md) | 中文

## Problem

Claude Code 的解析规则原本直接长在 `normalize.py`，`local_sessions.py` 也把 Claude 的 `meta.json` 闭集校验写死在导入路径里。接第二个 AI agent 时，如果继续在同一个 normalizer 里加 `runtime == ...` 分支，解析、重放、版本判断和数据库唯一键会一起变化；`trajectory_payloads.source_type` 又只表示 `script` / `http_api` 接入通道，无法表达“这条轨迹来自哪个 agent”。M9 还需要在证据、对象 revision 和归因缓存里区分 runtime，身份不先独立，后续数据必然混在一起。

## Decision

- 新增 `service/acquisition/parsers/`：`BaseTraceParser` 固定 JSONL 帧、坏行 issue、计数与 finalize，子类只实现 `consume_record` / `parse_agent_meta`；`TraceParserFactory` 用 `runtime_key` 注册和选择 parser，`parsers/__init__.py` 在包导入时自动发现同目录子模块。新增 runtime 只需新增一个子类文件并加 `@TraceParserFactory.register`，不改公共 normalize、replay 或 agent_tree。
- `normalize_transcript(...)` 保留为兼容 facade，默认 `claude-code`，新调用方显式传 `runtime_key`；`extract_evidence()` 作为可选 M9 接口默认返回空元组，Claude 的 agent/skill/file 证据留给 M9-02/M9-04。
- `runtime_key` 贯穿 `trajectory_payloads`、`source_records`、`session_families`、`agents` 和 replay：payload 主键与 source 唯一键都变成 `(runtime_key, root_session_id, agent_id)`，Session 记录产生它的 runtime，Agent 节点继承根会话 runtime。迁移把存量行回填为 `claude-code`。
- `parser_version` 从 parser 类读取，`source_records.parser_version` 只与同一 runtime 的当前版本比较；升级一个 runtime 只重放该 runtime 的 payload，另一个 runtime 的 cursor 与 Session 不变。
- 未知 runtime 抛 `UnsupportedTraceRuntime`，replay 写入稳定的 `UNSUPPORTED_RUNTIME`，不静默回退 Claude；根会话混用 runtime 时组装阶段报 `MIXED_TRACE_RUNTIME`。
- `source_type` 继续只表示接入通道，不参与 parser 选择。

## Alternatives considered

- **在 `normalize.py` 里按 runtime 加 if/else**：每接一个 agent 都改公共解析与重放文件，分支会继续扩散；拒绝。
- **未知 runtime 回退 Claude**：会把不兼容的 JSONL 误报成解析成功，破坏证据可信度；拒绝。
- **保留全局 `parser_version`**：升级 Claude 会强制重放其他 runtime，无法满足按 runtime 独立演进；拒绝。
- **让新 runtime 直接复用 `ParsedTranscript` 私有字段**：会把 provider 字段扩散成公共契约；拒绝。
- **在 M9-06 里实现第二个真实 runtime 或证据正文**：不属于本 issue 的交付边界，先建立扩展点和身份；留给后续 issue。

## Consequences

- 现在只有一个生产 parser；fake runtime 测试证明新增 runtime 不需要改公共 normalization/replay/agent_tree。
- 未知 runtime 的 payload 会一直保持待处理状态，因为系统没有可推进的 parser；这是有意暴露的运维信号，而不是静默吞掉。
- `session_families.id` 仍是全局主键，同一 root session id 不能跨 runtime 共存；当前上游不产生这种身份，若未来出现需要再评估复合键。
- 证据 hook 还没有真实内容，`agent_definition_hash`、Skill body 与文件读取证据在 M9-02/M9-04 才填充。
- `trajectory_payloads` 是外部写入表；runtime_key 迁移依赖默认回填，外部写入方升级前必须写显式 runtime，否则所有行都会被当成 Claude。
- 旧数据与旧脚本的 `source_type` 语义保持不变，前端暂时不展示 runtime。
