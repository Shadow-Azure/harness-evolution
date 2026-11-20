# 轨迹父子关系：会话级 link 接口与 ClaudeCodeTraceParser 实现

[English](m25-session-level-agent-link.en.md) | 中文

```yaml flow
kind: issue
id: m25-01
milestone: m25
depends:
  - m9-06
  - m9-03
priority: P1
status: ready
scope:
  - apps/api/app/service/acquisition/**
  - apps/api/tests/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 429
  url: https://github.com/Shadow-Azure/harness-evolution/issues/429
```

## 背景

生产 session `226504ab-f005-42ce-a9f5-8313c45d669e` 的执行流出现三个 `synthetic-agent`：三个子 Agent 都挂在 L1412–L1414，而不是各自的真实调用点 L1028 / L1202 / L1411；结构树标“合成”，lane DAG 三条子 lane 全部堆到约 78%。

已核对的直接原因：

- 上游会话包的 `agentMeta` 只透出 `name`，没有 `toolUseId`；原始数据里父 `toolUseResult.agentId` 与子 JSONL 顶层 `agentId` 是 3/3 精确对应的（`call_6424…→ad5308…`、`call_78b3…→a02a17…`、`call_b302…→a396a3…`），但当前 HE 不读这两处。
- `BaseTraceParser` 只有单 transcript 的 `normalize(payload)`；`ClaudeCodeTraceParser` 看不到同 root 的其它 transcript；`agent_tree` 只能拿 envelope 的 `parent_tool_use_id` / `parent_agent_id` 判断，缺失时走 `append_synthetic_parent_event`。
- 这与“子类能看到整个会话，父类加接口、子类实现”的设计意图不一致：缺少 session 级 link 钩子，跨 Agent 的 runtime 证据没有落点；上游缺 `toolUseId` 是主因，本 issue 在 HE 侧补设计缺口与可验证的 derived 兜底。

本 issue 把该意图落成显式契约：`link_transcripts(transcripts)` 在每个 root 上**一次**接收该 root 的全部 `ParsedTranscript`（主 Agent + 所有层级的子 Agent），`ClaudeCodeTraceParser` 在这一步能看到整个会话；逐 transcript 的 `normalize` 不变，`agent_tree` 只应用返回的链接。

## 目标

- 在 `BaseTraceParser` 增加 session 级 `link_transcripts` 钩子，默认返回空，不改变其它 runtime。
- `ClaudeCodeTraceParser` 实现钩子：优先使用 envelope 的 `toolUseId`（既有 authoritative 路径），缺失时用父 `toolUseResult.agentId` ↔ 子 JSONL 顶层 `agentId` 生成 `derived` 链接。
- `assemble_agent_trees` 按 root 调用钩子，`_assemble_root` 应用链接；无链接或歧义链接保留 `synthetic`，不伪造父子关系。
- 不改上游会话包、数据库 schema、共享契约或前端；存量 root 通过 `parser_version` 提升后重放重建。
- 明确可见性契约：`link_transcripts` 每个 root 只调用一次，入参是同 root 的完整 transcript 集合（main + 所有子 Agent）；子类在此完成跨 transcript 关联，`agent_tree` 只应用结果。

## 设计依据

- [01 §4.1 原始轨迹接入与归一化链路](../../../plans/fullstack-design/01-architecture.md)：`TraceParserFactory` 按 runtime 选子类，新增 runtime 只新增子类、不修改公共 replay/agent_tree；本 issue 把跨 Agent 扩展点收敛为父类钩子，由通用组装器调用。
- [06 §7.1 用户轮次/消息与 Agent 会话树派生](../../../plans/fullstack-design/06-database-design.md)：子 Agent 的 `*.meta.json.toolUseId` 指向父 Agent 调用，`agentId` 是子 Agent 身份；本 issue 在 envelope 缺 `toolUseId` 时用两处 `agentId` 兜底。
- [05 §10 轨迹查询接口](../../../plans/fullstack-design/05-api-design.md)：上游 payload 契约保持不变；本 issue 只定义 envelope 缺字段时的降级语义，不改契约。

## 实现内容

- `parsers/base.py`：新增 `AgentLink`（`child_agent_id`、`parent_tool_use_id`、`confidence`）与 `BaseTraceParser.link_transcripts(transcripts)` 默认空实现；`ParsedTranscript` 增加承载原生 `agentId` 与父 `tool_result.agentId` 映射的 typed 字段（`native_agent_id`、`agent_result_ids`）。
- `parsers/claude_code.py`：子 transcript 顶层 `agentId` 写入 `native_agent_id`；父记录 `toolUseResult.agentId` 按 `tool_use_id` 写入 `agent_result_ids`；实现 `link_transcripts`，只返回可唯一匹配的 `derived` 链接，冲突/缺失不返回；`parser_version` 6→7。
- `agent_tree.py`：`assemble_agent_trees` 按 root 的 `runtime_key` 创建 parser 并调用 `link_transcripts`；`_assemble_root` 在 `parent_tool is None` 时查链接，命中后设置 `parent_tool` 并标 `derived`，未命中保留 `synthetic`。
- 调用约定：`assemble_agent_trees` 对每个 root 只调用一次 `parser.link_transcripts(transcripts)`，传入该 root 的全部 transcript（稳定顺序）；`agent_tree` 不读取 `agentId` / `toolUseResult` 等 Claude 字段，只消费 `AgentLink`。
- 优先级保持：envelope 的 `toolUseId` / authoritative 关联不变；derived 只填补缺失；`synthetic` 仍覆盖缺失与歧义，不覆盖已有 authoritative。
- 测试：主 + 3 子 fixture、缺失/重复/歧义/无链接分支、API tree 断言；生产验收只读 226504ab，不把其内容提交仓库。

## 实施步骤

1. 在 `parsers/base.py` 定义 `AgentLink`、`ParsedTranscript` 字段与 `BaseTraceParser.link_transcripts` 默认实现。
2. 在 `parsers/claude_code.py` 提取两处 `agentId`，实现 `link_transcripts`，提升 `parser_version`。
3. 在 `agent_tree.py` 的 `assemble_agent_trees` 中，对每个 root 用完整 transcript 集合调用一次 `link_transcripts`，把链接传入 `_assemble_root`。
4. 在 `_assemble_root` 应用 derived 链接，保持 authoritative / derived / synthetic 的优先级。
5. 补单测与 API 测试，跑聚焦门禁；部署后 replay/backfill，核对 226504ab。
6. 更新 Agent Note 与流程状态；PR 附修复前后的真实应用截图。

## 依赖与交付边界

- 依赖：m9-06（parser 工厂）、m9-03（关系证据）；两者均已完成。
- 交付边界：只改 HE 的 acquisition parser/agent_tree 与测试；不改上游 envelope；不改 DB schema / 共享契约 / 前端；不触碰其它 runtime 的解析行为；生产 Session 内容与截图不入库。

## 独立验证

```sh
pnpm test:api -- -k "claude_code_parser or agent_tree or sessions"
pnpm test:gates
pnpm verify:flow
pnpm verify:flow-online
```

- 预期：单测覆盖主 + 3 子 fixture，3/3 链接命中；歧义/缺失走 synthetic；API tree 无 synthetic；其它 runtime 与既有 fixture 不回归；流程在线一致。
- 生产验收：部署后对 226504ab 触发 replay，`GET .../tree` 的 3 个子 Agent `toolUseId` 为 `call_6424… / call_78b3… / call_b302…`，`relationConfidence=derived`，lane DAG 子 lane 起于 L1028 / L1202 / L1411；Before/After 截图入 PR。

## 验收标准

- `BaseTraceParser.link_transcripts` 默认返回空；未实现该钩子的 runtime 行为不变，`synthetic` 兜底仍覆盖缺失与歧义。
- `ClaudeCodeTraceParser` 能从原始 JSONL 提取 3/3 `agentId` 并生成唯一 derived 链接；`agent_tree` 把 3 个子 Agent 挂到真实 `call_…`，结构树与 lane DAG 不再出现 `synthetic-agent`。
- 无链接、重复 `agentId`、同一 `agentId` 多个父（歧义）时保留 `synthetic` 并记录稳定 issue，不误挂。
- `parser_version` 提升后 replay 可重建存量树；无 DB/契约/前端 diff；聚焦测试、流程与文档门禁通过；PR 含 Before/After 证据。
- 单测断言 `link_transcripts` 在同 root 的完整集合（main + 3 子）上调用一次，子类实现能同时看到 4 个 transcript；未实现钩子的 runtime 返回空且行为不变。

## 门禁与 CI

- 命中：`pnpm test:api`、`pnpm test:gates`、`pnpm verify:flow`、`pnpm verify:flow-online`、`pnpm lint:api`、`pnpm typecheck:api`、`pnpm verify:docs`。
- 不新增依赖；scope 覆盖 parser、agent_tree、API 测试、docs/flow；CI 使用合成/脱敏 fixture。

## 非目标

- 不修改评估平台会话包与 `toolUseId` 透传（另立上游 issue）。
- 不改前端 lane DAG / 结构树布局或共享契约字段。
- 不新增数据库列/迁移；不改 bad case 锚点、归因或自进化算法。
- 不把生产 Session 内容、截图或凭据提交到仓库。
