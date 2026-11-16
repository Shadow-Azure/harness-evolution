# 上报会话来源字段与多 runtime 会话源适配器工厂

[English](m9-07-per-report-session-source.en.md) | 中文

```yaml flow
kind: issue
id: m9-07
milestone: m9
depends:
  - m9-06
priority: P1
status: done
scope:
  - apps/api/app/third_party_api/session_source/**
  - apps/api/app/third_party_api/session_query/**
  - apps/api/app/service/acquisition/**
  - apps/api/app/service/workspaces/**
  - apps/api/app/api/ingest.py
  - apps/api/app/db/**
  - apps/api/alembic/**
  - apps/api/app/errors.py
  - apps/api/app/main.py
  - packages/contracts/**
  - apps/api/tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 282
  url: https://github.com/Shadow-Azure/harness-evolution/issues/282
```

## 背景

当前 bad case 上报（`POST /api/workspaces/{wid}/bad-cases`）只携带问题字段与 `sessionId`；轨迹补齐完全依赖全局唯一的查询服务（`HE_SESSION_QUERY_BASE_URL` + 服务令牌，children/trajectory 两个接口），且该契约隐含 Claude Code 形状：`BadCaseRootSyncService` 写入 payload 时 `runtime_key` 取默认值 `claude-code`，上游没有通道声明"这条会话由哪个 AI agent 产生、去哪里下载"。

多上游场景下这一假设失效：不同团队使用不同 agent（Claude Code、opencode 等），会话存储形状完全不同——Claude Code 是 JSONL 行加 `*.meta.json`；opencode 是 session/message/part 对象（`parent_id` 表达父子、`modelID/providerID` 表达模型、tool part 表达调用）。全局单一 URL 既无法按上报路由到正确上游，也无法让 m9-06 建立的 `TraceParserFactory` 拿到真实 `runtime_key`。

## 目标

- 上报 API 新增可选 `sessionSource` 字段（dict）：携带按 sessionId 下载会话信息的 URL 模板，可选预声明 runtime。
- 定义单接口"会话信息 envelope"：一次调用返回 runtime 身份、agent 元数据、父子关系与规范化轨迹；`runtime` 字段决定 key-value 的解释方式。
- 建立 `SessionSourceFactory`、`BaseSessionSourceAdapter` 与 `ClaudeCodeSessionSourceAdapter`，模式对齐 m9-06 parser 工厂：新 agent 只新增一个子类文件并注册，公共 root-sync/normalize 不改。
- root-sync 按 root 选择来源：per-report source 优先、全局配置源回退；来源快照落状态表，重试不换源。
- runtime 身份保持单一 home：envelope `runtime` → source adapter → `TraceParserFactory` 选 parser；未知 runtime 稳定报错，不静默回退 Claude。

## 设计依据

- [05 §3.8 bad case 上报](../../../plans/fullstack-design/05-api-design.md#38-bad-case-上报)：上报 body 契约与新字段落点。
- [05 §10.1 会话轨迹包](../../../plans/fullstack-design/05-api-design.md#101-会话轨迹包核心)：单接口会话包的既有草案；本 issue 将其泛化为 per-report 绑定与 runtime 类型化。
- [06 §3.0.1 runtime 身份](../../../plans/fullstack-design/06-database-design.md#301-runtime-身份与-parser-版本)：runtime_key 词汇表与 parser 选择唯一键。
- [06 §4.1 bad_cases](../../../plans/fullstack-design/06-database-design.md)：问题表列演进。
- [07 §2.6 多 runtime parser 工厂](../../../plans/fullstack-design/07-backend-implementation.md#26-多-runtime-parser-工厂)：工厂、基类、自注册与 fail-fast 模式。
- [11 §3 外部查询服务契约](../../../plans/fullstack-design/11-bad-case-session-sync.md#3-外部查询服务契约)：现有两接口的串行锁、限额与错误语义。
- [11 §3.2 接口 2](../../../plans/fullstack-design/11-bad-case-session-sync.md#32-接口-2单-agent-轨迹)：NDJSON 规范化与上限规则，本 issue 复用。
- [11 §4.2 agent_meta 与父子边](../../../plans/fullstack-design/11-bad-case-session-sync.md#42-agent_meta-与父子边)：parentAgentId 回退锚边。
- [11 §5.1 表 bad_case_root_sync](../../../plans/fullstack-design/11-bad-case-session-sync.md#51-表-bad_case_root_sync)：状态表演进。

## 实现内容

**上报字段**：`BadCaseIngest` 新增可选 `sessionSource`（camelCase、`extra="forbid"`，校验失败 422）：

```json
{
  "runtime": "claude-code",
  "sessionUrlTemplate": "https://trace.internal/api/sessions/{sessionId}"
}
```

- `sessionUrlTemplate` 必填：http/https、长度 ≤ 2048、`{sessionId}` 占位符恰出现一次；不收 headers/token 等凭据字段，授权由模板自带短时签名承担。
- `runtime` 可选：`^[a-z0-9][a-z0-9-]{0,31}$`，仅作预声明；最终以 envelope 回报为准，不一致记诊断不失败。
- 不带 `sessionSource` 的上报行为与现状完全一致（向后兼容）。

**会话信息 envelope**（单接口：模板代入 sessionId 后 GET，JSON）：

```json
{
  "schemaVersion": 1,
  "sessionId": "0ab6…",
  "runtime": "claude-code",
  "runtimeVersion": "2.0.14",
  "agentKind": "main",
  "parentSessionId": null,
  "childSessionIds": ["agent-a1", "agent-b2"],
  "agentMeta": { "agentType": "general-purpose", "spawnDepth": 1 },
  "trajectory": { "format": "ndjson", "lineCount": 812, "content": "…" },
  "updatedAt": "2026-11-16T18:00:00+08:00"
}
```

- `runtime` 是 AI agent 类型的封闭键，与 parser `runtime_key` 同一词汇表；决定 envelope 的 key-value 解释归哪个 adapter 子类。
- `agentMeta` 是 runtime 专属 key-value 区：Claude Code 为 meta.json 形状（agentType/spawnDepth/toolUseId/teamName 等），opencode 为 parent_id/modelID/providerID 等投影所需字段；每种 runtime 一套 closed schema，解释内聚在子类。
- `childSessionIds` 只返回一层直接子会话；遍历沿用现有 BFS 与 visited/深度/数量/时间预算限额，逐层代入模板。
- `trajectory.content` 沿用 [11 §3.2](../../../plans/fullstack-design/11-bad-case-session-sync.md#32-接口-2单-agent-轨迹) 的规范化规则（重序列化、重复 key 拒绝、64 MiB/单行 1 MiB/100 万行上限），实现从 `HttpSessionQuerySource` 抽出共享。
- 校验：`schemaVersion` 主版本不匹配 → `SESSION_SOURCE_VERSION_INCOMPATIBLE`；`sessionId` 回显不一致 → `SESSION_SOURCE_SESSION_MISMATCH`；`agentKind=subagent` 时 `parentSessionId` 必须等于遍历父节点；`trajectory.format` v1 仅 `ndjson`。

**适配器工厂**：

```text
apps/api/app/third_party_api/session_source/
  __init__.py       # auto-discover + register
  base.py           # BaseSessionSourceAdapter + SessionInfo + envelope model
  factory.py        # SessionSourceFactory
  claude_code.py    # ClaudeCodeSessionSourceAdapter
  <runtime>.py      # new agent adds only this file
```

- `BaseSessionSourceAdapter` 模板方法：envelope 严格校验与 HTTP 细节（超时、重试、进程级串行锁，语义对齐 11 §3）在基类与共享客户端；子类只实现 `parse_agent_meta` 与 `project`，把 runtime 专属 key-value 投影到 runtime 无关的 `SessionInfo`（runtime_key、agentKind、parentAgentId、childSessionIds、agent_meta、规范化 trajectory）。
- `@SessionSourceFactory.register` 自注册：重复 `runtime_key` fail-fast；未知 runtime 抛 `UnsupportedTraceRuntime`（复用 m9-06 语义）。
- adapter `runtime_key` 必须命中已注册 parser；`SessionInfo.runtime_key` 即 `TraceParserFactory.create` 的选择键，runtime 身份不出现第二个 home。
- 测试用 fake runtime 子类验证扩展路径（对齐 m9-06 的 fake parser 测试）。

**根同步来源选择与持久化**：

- `bad_cases` 新增 `session_source` JSON NULL 列；`bad_case_root_sync` 新增 `source_kind`（`report`/`global`，存量回填 `global`）与 `source_snapshot` JSON NULL；双方言迁移。
- 选择规则：同一 root 取 `created_at` 最新且非空的 `session_source`（并列取最大 `bad_case_id` 保证确定）；没有 per-report source 的 root 回退全局配置源，现有两接口路径不动。
- claim 时固化 `source_snapshot`（runtime 预声明 + URL 模板），重试不换源；显式 source 失败即 root 失败（`SESSION_SOURCE_*` 稳定码），不静默降级到全局源。
- `write_local_payloads` 写入的 `runtime_key`/`agent_meta` 来自 `SessionInfo` 投影：subagent 可带真实 `parentAgentId`（乃至 `toolUseId`），改善 11 §4.2 的锚边精度；main agent 的 `agent_meta` 存 envelope `agentMeta`（可为空）。

**契约与文档**：OpenAPI 增加 `BadCaseIngest.sessionSource`，`pnpm contract:generate` 后过 `contract:check`，生成类型禁止手改；同步 05（§3.8 字段、§10 增补 per-report envelope 小节）、06（bad_cases/bad_case_root_sync 列）、07（session_source 工厂）、11（来源选择）；补一条 Agent Note 说明 envelope 契约与新 runtime 接入步骤。

## 实施步骤

1. 失败测试先行：ingest `sessionSource` 校验（占位符缺失/重复、超长、非 http(s)、多余凭据字段）；envelope 解析（版本不匹配、回显不一致、未知 runtime、坏 NDJSON、`agentMeta` 不符子类 closed schema）。
2. 实现 `third_party_api/session_source/` 包：基类、工厂、严格 envelope 模型与 Claude 子类；抽取共享的 trajectory 规范化。
3. 双方言迁移：`bad_cases.session_source`、`bad_case_root_sync.source_kind/source_snapshot` 与回填。
4. root-sync 来源选择、快照与 per-report 遍历；replay 验证 `runtime_key` 贯穿。
5. 契约再生成；fake runtime 子类扩展测试；文档与 Agent Note。

## 依赖与交付边界

- 依赖：m9-06
- 非目标：见下。

## 独立验证

```sh
pnpm test:api -- tests/m9-07-report-session-source
pnpm test:db
pnpm test:db:mysql
pnpm contract:check
pnpm verify:flow
```

- 带 `sessionSource` 的上报落库后，root-sync 按模板 URL 拉取，envelope `runtime` 选中 adapter 与 parser，`runtime_key`/`agent_meta` 正确落库。
- 不带 `sessionSource` 的上报回退全局源，行为与现状一致。
- fake runtime 只注册子类即可被 root-sync 选中，公共 root-sync/normalize 无改动。
- 未知 runtime/坏 envelope：root 标 `failed`，`last_error` 为稳定码，不进入 Claude parser。

## 验收标准

- 上报契约向后兼容：不传 `sessionSource` 的旧调用行为不变。
- envelope 单接口可重建主/子树（childSessionIds 递归），runtime_key 贯穿 payload、source_records、session_families。
- 新增 runtime 只新增 `session_source/<runtime>.py` 与 `parsers/<runtime>.py` 并注册。
- 未知 runtime、版本不匹配、回显不一致均为稳定错误码，无静默回退。
- 契约、双方言迁移、flow 与 docs 门禁全绿。

## 门禁与 CI

- API 单测、双方言数据库、契约、flow 与 docs 门禁。

## 非目标

- 不实现第二个真实 runtime（如 opencode）的完整解析，仅留扩展位与测试 fake。
- 不改目录同步（bad_case_query 上游）契约。
- 不收上报方凭据字段，不在库内保存认证信息。
- 不做轨迹内容增量变更检测与自动重拉。
- 不改前端展示，不做多实例跨进程锁。
