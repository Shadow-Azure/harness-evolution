# 多 Agent 轨迹 Parser 工厂与 runtime 身份

[English](m9-06-runtime-parser-factory.en.md) | 中文

```yaml flow
kind: issue
id: m9-06
milestone: m9
depends:
  - m7-02
priority: P0
status: in-progress
scope:
  - apps/api/app/service/acquisition/**
  - apps/api/app/api/acquisition.py
  - apps/api/app/db/**
  - apps/api/alembic/**
  - packages/contracts/**
  - apps/api/tests/**
  - tests/**
  - docs/**
  - plans/**
  - plans/fullstack-design/**
  - plans/ui-prototype-v2/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 277
  url: https://github.com/Shadow-Azure/harness-evolution/issues/277
```

## 背景

当前 `service/acquisition/normalize.py` 只理解 Claude Code 的 `assistant/user/attachment`、`isMeta`、`message.content` 和 Claude subagent `meta.json`；`local_sessions.py` 也直接校验 Claude 元数据。`trajectory_payloads.source_type` 只是 `http_api/script` 接入通道，不能表达 AI agent 类型；`parser_version` 又是全局整数。继续在单一 normalizer 里加 `runtime == ...` 分支，接入第二个 agent 时会同时修改解析、replay、版本判断和数据库唯一键。

M9 又需要按 agent/skill 定义和文件读取建立对象 revision。若 runtime 身份不先独立，后续证据、潜在匹配和归因缓存都会把不同 agent 的数据混在一起。

## 目标

- 建立 `TraceParserFactory`、`BaseTraceParser` 与 `ClaudeCodeTraceParser`，把 Claude 专有解析收进子类。
- 用 `runtime_key` 贯穿 payload、source cursor、Session 和 replay；`source_type` 保持接入通道语义。
- `parser_version` 按 runtime 解释，避免新增 runtime 被 Claude 的全局版本号误判。
- 未知 runtime 生成稳定诊断，不静默回退到 Claude。
- 新 runtime 只新增 parser 子类并注册，不修改 `normalize.py`、`replay.py`、`agent_tree.py`。

## 设计依据

- [07 §2.6 多 runtime parser 工厂](../../../plans/fullstack-design/07-backend-implementation.md#26-多-runtime-parser-工厂)：基类、工厂、子类与注册方式。
- [06 §3.0.1 runtime 身份](../../../plans/fullstack-design/06-database-design.md#301-runtime-身份与-parser-版本)：`runtime_key`、per-runtime `parser_version` 与唯一键。
- [15 §9.2 对象 revision 与模型身份](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md#92-对象-revision-与模型身份)：证据字段与 runtime 版本分离。

## 实现内容

- 新增 `app/service/acquisition/parsers/`：`base.py`、`factory.py`、`claude_code.py`，包启动时自动发现并注册子类。
- `BaseTraceParser` 负责 JSONL 帧、坏行 issue、隐私边界、计数与 finalize；子类负责 record/meta/event/evidence 解释。
- `@TraceParserFactory.register` 注册子类；重复 `runtime_key` 直接失败；未知 runtime 抛 `UnsupportedTraceRuntime`。
- `trajectory_payloads`、`source_records`、`session_families` 增加 `runtime_key`，存量回填 `claude-code`；`source_records` 的待处理判断带 runtime。
- `RootPayload`、replay 和 acquisition API 传递 `runtime_key`；保留 `normalize_transcript` 兼容 facade。
- `BaseTraceParser.extract_evidence()` 作为 M9 可选 hook；本 issue 只建立接口，Claude 的 agent/skill/file 证据由 M9-02/M9-04 填充。

## 实施步骤

1. 先写 factory 注册、重复 key、未知 runtime、默认 Claude 的失败测试。
2. 抽出 `BaseTraceParser` 与 `ClaudeCodeTraceParser`，保持现有 normalize 测试全绿。
3. 增加 runtime_key 迁移、`RootPayload` 字段和 per-runtime parser version 查询。
4. 接入 replay 与 acquisition API，补未知 runtime 的 sync issue。
5. 补“新增 fake runtime 子类 + 注册”的扩展测试与 Agent Note。

## 依赖与交付边界

- 依赖：m7-02
- 非目标：不实现第二个真实 runtime；不解析 M9 的 agent/skill/file 证据正文；不改前端展示。

## 独立验证

```sh
pnpm test:api -- tests/acquisition tests/replay
pnpm test:db
pnpm contract:check
pnpm verify:flow
```

- Claude fixture 全部保持原有计数与事件。
- 测试专用 fake runtime 只注册子类即可被 replay 选中。
- 未知 runtime 产生 `UNSUPPORTED_RUNTIME`，不进入 Claude 解析器。
- 升级一个 runtime 的 parser version 不重放另一个 runtime。

## 验收标准

- 新增 runtime 不需要修改公共 normalization/replay 文件。
- `runtime_key` 在 payload、source cursor、Session 和 replay 中一致。
- `source_type` 不再被当作 runtime 使用。
- 现有 E2E/数据库/契约门禁不回归。

## 门禁与 CI

- API 单测、双方言数据库、契约、flow 与 docs 门禁。

## 非目标

- 不实现 Codex 或其他真实 agent 的解析规则。
- 不把 provider 私有字段扩散到 `ParsedTranscript` 公共字段。
- 不保存消息、工具输出或 agent 定义正文。
