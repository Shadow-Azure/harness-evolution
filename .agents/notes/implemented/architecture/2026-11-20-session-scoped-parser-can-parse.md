# Agent Note: 会话级 parser 与 can_parse 轨迹选型

Status: implemented

[English](2026-11-20-session-scoped-parser-can-parse.en.md) | 中文

## Problem

Session `226504ab-f005-42ce-a9f5-8313c45d669e` 的执行流把三个子 Agent 画成 `synthetic-agent`：envelope 的 `agentMeta` 缺 `toolUseId`，而当前 `BaseTraceParser.normalize(payload)` 一次只处理一个 Agent 的 JSONL，`ClaudeCodeTraceParser` 在归一化阶段看不到同 root 的其它 transcript，父子关联只能由 `agent_tree` 用弱字段兜底。用户要求改为“创建子类时把整个会话主/子轨迹初始化到成员变量”，并“选择 parser 也根据轨迹来”，新增 `can_parse` 判断子类能否初始化某条轨迹（[issue #429](https://github.com/Shadow-Azure/harness-evolution/issues/429)）。

设计文档仍写着 `TraceParserFactory` 按 `runtime_key` 选子类、parser 逐 payload 归一化、新增 runtime 不改公共 replay/agent_tree（[01 §4.1](../../../../plans/fullstack-design/01-architecture.md)、[06 §3.0.1](../../../../plans/fullstack-design/06-database-design.md)、[07 §2.6](../../../../plans/fullstack-design/07-backend-implementation.md)）。若不先修订，实现会直接违背设计文档；这正是本 Note 记录、并在同一 PR 修订文档的原因。

## Decision

- Parser 选型改为**轨迹内容**驱动：`BaseTraceParser.can_parse(payloads)` 是抽象类方法，由子类做快速形态探测；`TraceParserFactory.for_trace(payloads)` 在已注册子类中唯一命中后实例化，零命中 `UnsupportedTraceRuntime`、多命中 `AmbiguousTraceRuntime`，不按注册顺序静默选。`runtime_key` 保留为 runtime 身份与存储键，不再是唯一选择依据。
- Parser 生命周期改为**会话级**：构造函数接收同一 root 的全部 `TracePayload`（主 Agent + 所有层级子 Agent），初始化 `payloads` / `main` / `subagents` 成员；`normalize_session()` 逐 payload 归一化并调用子类的 `link_transcripts()`，一次返回 transcripts 与 `AgentLink`。
- 父子关联优先级：envelope `toolUseId` 为 authoritative；缺失时用父 `toolUseResult.agentId` ↔ 子 JSONL 顶层 `agentId` 生成 derived；无链接/歧义保留 synthetic。`agent_tree` 只应用链接，不读取 Claude 私有字段。
- 三条入口（replay / local / normalize）先按 root 取齐 payloads，再 `for_trace` 创建会话 parser，再 `normalize_session`；单 payload `normalize(payload)` 保留为兼容入口。
- 生命周期与内存：parser 每个 root 一个实例，只持有已加载 payloads 的引用，不复制原始 JSONL；`normalize_session` 后释放，不跨 root 复用、不引入跨请求缓存。
- 同步修订 [01 §4.1](../../../../plans/fullstack-design/01-architecture.md)、[02 F9](../../../../plans/fullstack-design/02-features.md)、[04 parser 扩展点](../../../../plans/fullstack-design/04-backend-architecture.md)、[05 envelope](../../../../plans/fullstack-design/05-api-design.md)、[06 §3.0.1/§7.1](../../../../plans/fullstack-design/06-database-design.md)、[07 §2.3/§2.5/§2.6](../../../../plans/fullstack-design/07-backend-implementation.md)、[09 R10/R17](../../../../plans/fullstack-design/09-review-guide.md)、[15 多 runtime 缺口](../../../../plans/fullstack-design/15-v1-v2-gap-analysis.md) 与 [README D24](../../../../plans/fullstack-design/README.md)；实现随本 PR 落地（#429）。

## Alternatives considered

- **B 方案：无状态 parser + 会话级 link 钩子。** 改动最小、不持有全量 payload，但只解决了父子关联，没有落成用户要求的“构造时把整个会话初始化到成员变量”；用户明确改为 A，故否决。
- **保留 runtime_key 选型，只加 can_parse 做校验。** 选型仍不能处理 runtime_key 缺失/错标或同 runtime 多形态的轨迹；与“根据轨迹选择”的要求不符，故否决。
- **构造注入成员变量但不引入 can_parse。** 生命周期符合 A，但选型仍依赖调用方给的 runtime_key；无法满足“由轨迹判断能否初始化”，故否决。
- **逐 payload parser + 传递 SessionContext。** 比 B 更接近会话模型，但 parser 仍不是“构造即会话”，用户要的成员变量语义不成立；且仍需改公共编排，收益不如直接采用会话级构造，故否决。

## Consequences

- 设计文档与实现契约一致：选型、生命周期、链接优先级不再各说各话；实现已随本 PR 落地。
- Parser API 变化：`__init__(payloads)`、`can_parse`、`normalize_session`、`for_trace`；`create(runtime_key)` 与 `normalize(payload)` 退为显式/兼容入口，现有调用方需按 #429 迁移。
- 每个 root 的 parser 持有全部 payload 引用；大 session 的峰值内存受已加载 payloads 约束，不做额外复制；parser 不跨 root 复用。
- 选型错误从“未知 runtime”扩展为“未知轨迹/歧义轨迹”；错误码与诊断需在实现中稳定化。
- 存量 root 需要 `parser_version` 提升后 replay/backfill；无 DB schema、共享契约或前端变更。
- 01 §4.1 的“新增 runtime 不改公共 replay/agent_tree”改为“公共 session 编排通用、新 runtime 只实现子类钩子”；新增 runtime 仍需 `can_parse` 与会话链接实现。
