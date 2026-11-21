# Claude Code 子 agent 定义 prompt 未解析：识别 attachment 嵌套 prompt_snapshot 并传播父事件 definitionHash

[English](bugfix-claude-agent-attachment-prompt.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-12
milestone: bugfix
depends:
  - m9-02
  - m9-04
  - m9-07
priority: P2
status: in-progress
scope:
  - apps/api/app/service/acquisition/parsers/**
  - apps/api/app/service/acquisition/agent_tree.py
  - apps/api/tests/**
  - docs/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-21-claude-attachment-prompt-snapshot.md
github:
  number: 471
  url: https://github.com/Shadow-Azure/harness-evolution/issues/471
```

## 背景

生产 OpenSpec-cn 轨迹的 agent 关联为 0：57 个已导入 Session 的 tree 中 `agent_definition_hash` 为 0，73/73 个 agent 事件 `objectRevision=unknown`。此前只能从平台 API 看到解析后的 tree，无法区分“上游没给定义”和“解析器没读到定义”。

2026-11-21 通过生产 root SSH 读取 `bad_cases.session_source` 并实际调用真实 `sessionUrlTemplate` 后确认：

- 样本是一个 main + 6 个 subagent 的 Claude Code 会话；
- child envelope 的 `trajectory.content` 里没有顶层 `type=prompt_snapshot`；
- 定义正文实际在 `type=attachment`、`attachment.type=prompt_snapshot` 的 `attachment.systemPrompt[0]`；
- 对 6 个 child 的 `attachment.systemPrompt[0]` 按平台归一化算 SHA-256：`code-generator` 为 `c816a39e…`、`spec-reviewer` 为 `86b6567b…`、`code-quality-reviewer` 为 `3742e03f…`，6/6 与镜像 a7ec200 的目标 `AGENT.md` digest 一致；
- child `agentMeta` 只有 `{"name": "..."}`，不是 `promptSnapshot`；因此根因不是 `agentMeta.promptSnapshot` 被丢。

另有第二个阻断：子 agent 的 `agentMeta` 只有 `name`、没有 `agentType`，而 `_agent_revision` 依赖 `agentType`；即使 attachment 修复产出 `agent_definition_hash`，`agent_revision` 仍为 None。`agent_tree._apply_agent_revisions` 只在 revision 非空时把 child 的 `definition_hash` 挂到父 `kind=agent` 事件，所以父事件仍是 `unknown`，matcher 仍匹配不到。

当前 `ClaudeCodeTraceParser.consume_record` 只在 `record_type in {"prompt_snapshot","api-request-shape"}` 时调用 `_record_agent_definition`；`record_type == "attachment"` 只用于 `skill_listing` 的 digest，不检查 `attachment.type`。`_definition_body` 对 `api-request-shape` 还按顶层 `record["system"]` 读取，实际数据在 `record["shape"]["system"]`。因此 0 hash 的直接根因是 **Claude 解析子类的 record shape 识别缺口**，不是数据缺失，也不是匹配算法或 target 配置问题。

## 目标

- 在 Claude Code 子类中识别 `type=attachment` 且 `attachment.type=prompt_snapshot` 的记录，读取 `attachment.systemPrompt`，产出 `agent_definition_hash` 与 `definition_source`。
- 在 `agent_tree._apply_agent_revisions` 中，即使 child revision 为 None，只要 `agent_definition_hash` 存在，也把 `definition_hash` 挂到父 `kind=agent` 事件；matcher 用 `definition_hash` 命中 target body hash。
- 使用与目标侧一致的归一化规则，使 6 个 OpenSpec-cn agent 的 digest 与镜像 `AGENT.md` 对上。
- 通过 `parser_version` 升级让已存 payload 重放，无需重新拉取上游、无需改数据库。
- 保持现有顶层 `prompt_snapshot` / `api-request-shape` 行为不回归。

## 设计依据

- [07 §2.3 归一化](../../../plans/fullstack-design/07-backend-implementation.md#23-归一化行数组--中间结构)
- [07 §2.4 Agent 会话树组装](../../../plans/fullstack-design/07-backend-implementation.md#24-agent-会话树组装)
- [07 §2.6.1 会话来源适配器工厂（M9-07）](../../../plans/fullstack-design/07-backend-implementation.md#261-会话来源适配器工厂m9-07)
- [05 §10.5 上报绑定的会话信息 envelope](../../../plans/fullstack-design/05-api-design.md#105-上报绑定的会话信息-envelopem9-07)

## 实现内容

- 在 `ClaudeCodeTraceParser.consume_record` 的 `attachment` 分支增加：当 `attachment.type == "prompt_snapshot"` 时，把 `attachment.systemPrompt` 交给既有的 `_record_agent_definition`（可合成 `{"systemPrompt": ...}` 或抽一个私有 helper）。
- `_definition_body` 继续取 `systemPrompt` 列表的第一项；实际数据的第一项就是目标 `AGENT.md` 正文，hash 已实测匹配。
- 仅在 attachment 路径上取正文；不把 `api-request-shape.shape.system` 当定义正文（其 hash 与目标不一致）。
- `parser_version` 从 7 升到 8；`source_records.parser_version` 触发重放，现有 payload 中的 attachment 可直接重算。
- 父事件传播改动在 `agent_tree._apply_agent_revisions`：revision 为空时仍写 `definition_hash`，不改变 `agent_revision = agentType + isBuiltIn + body hash` 的诊断语义。
- 增加解析单测：attachment 形状 → `agent_definition_hash`；父 agent 事件 → `digest:` revision。
- 补一条 Agent Note，记录“prompt 定义可能出现在 attachment 嵌套形状”的决策与边界。
- 设计文档：`07 §2.3` 与 `15 §9.2` 记录真实嵌套形状；Agent Note 回链本 issue。

不改 `AgentMetaFacts` 基类、`TargetObjectType` / `TARGET_FILE_NAMES`、matcher、数据库 schema 或契约。

## 实施步骤

1. 在 `claude_code.py` 增加 attachment prompt_snapshot 识别与 hash 写入。
2. 增加单测：`type=attachment` + `attachment.type=prompt_snapshot` + `systemPrompt` 列表，断言 hash 与 `definition_source`；父事件 revision；无 prompt 的 attachment 不误报。
3. 升 `parser_version`，确认 replay 会重新归一化已存 payload。
4. 补 Agent Note，更新 flow 文档中的相关说明（如需要）。
5. 运行独立验证与门禁；在测试环境创建 agent target，确认预览能关联到目标 Session。

## 依赖与交付边界

- 依赖：m9-02、m9-04、m9-07。
- 交付边界：只修复 Claude Code parser 子类对 attachment 嵌套 prompt_snapshot 的识别；不改变对象模型、匹配算法、数据库或上游契约。
- 本次 issue 不包含生产 run、不重放生产数据、不创建 agent target；这些属于验收后的操作步骤。

## 独立验证

```sh
pnpm test:api -- tests/m9-02-trace-metadata-completion-parser
pnpm lint:api
pnpm typecheck:api
pnpm test:gates
pnpm verify:flow
```

- 新增用例断言 `agent_definition_hash == c816a39e…`（或测试 fixture 对应 digest），`definition_source == "prompt_snapshot"`，父事件 `object_revision == "digest:<hash>"`。
- 既有顶层 `prompt_snapshot` / `api-request-shape` 用例保持通过。
- `pnpm verify:flow` 通过，issue 三件套配对与正文契约完整。

## 验收标准

- 用合成 attachment fixture 解析后，子 agent 出现 `agent_definition_hash`，父 `kind=agent` 事件的 `definitionHash` 等于该 hash；若 child 有 `agentType`，同时出现 `digest:` revision。
- 对实际 templateUrl 样本，6 个 child 的 `attachment.systemPrompt[0]` 分别命中 `c816a39e…` / `86b6567b…` / `3742e03f…`；父事件带同名 `definitionHash`；创建 agent target 后，向导预览至少能关联到对应 Session。
- 既有 `prompt_snapshot` / `api-request-shape` 路径无回归；测试、lint、typecheck、flow 门禁全绿。

## 门禁与 CI

- `pnpm test:api -- tests/m9-02-trace-metadata-completion-parser`
- `pnpm lint:api`、`pnpm typecheck:api`
- `pnpm test:gates`、`pnpm verify:flow`
- 若改动文档/Agent Note，运行 `pnpm verify:docs` 与 `pnpm record:i18n -- <pair>`。

## 非目标

- 不修改 `AgentMetaFacts` 基类、`TargetObjectType`、`TARGET_FILE_NAMES`、matcher 或数据库 schema。
- 不按 agent 名字做匹配；不为任意未知字段做启发式猜测。
- 不处理 envelope 顶层 `promptSnapshot`、根 agent 整包全文切分、主 agent `agentMeta` 映射子 agent 等形状；这些若需要，另开 issue。
- 不重放生产数据、不创建/启动生产 agent target、不修改生产凭据或 templateUrl。
