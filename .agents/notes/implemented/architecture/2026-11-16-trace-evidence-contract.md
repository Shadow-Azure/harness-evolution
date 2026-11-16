# Agent Note: 轨迹证据字段与执行闭环契约

Status: implemented

[English](2026-11-16-trace-evidence-contract.en.md) | 中文

## Problem

M9-06 已经让 parser 和 runtime 身份独立，但会话树仍只有解析健康 `status` 和 linked/unlinked 关系，无法表达父工具未返回、子 Agent 没有最终报告、外部 attempt 失败，也没有字段承载对象 revision、Agent/Skill 定义指纹和文件读取证据。若这些状态继续挤进 `status` 或自由文本，前端、归因和后续 run 会把“解析成功”误当成“执行完成”。

## Decision

- 新增迁移 `0016`，按 [06 §3.3–§3.4](../../../../plans/fullstack-design/06-database-design.md) 就地扩展三张轨迹表：`session_families.execution_outcome/end_reason`、`agents.execution_outcome/end_reason/agent_definition_hash/definition_source`、`agent_events.object_revision/definition_hash/file_read_hash/read_complete/relation_confidence`。
- `execution_outcome` 是非空封闭状态 `completed / interrupted / failed / legacy_unknown`，加列时由 NOT NULL 默认值覆盖存量行；`end_reason`、关系置信度、定义/文件 hash 与 `read_complete` 可空，存量保持 NULL。迁移按列存在性守卫，MySQL 部分 DDL 失败后重跑只补缺失列；同时支持 SQLite 与 MySQL，`runtime_key`、`parser_version` 不动。
- `session_families.status` 继续只表达解析健康；执行闭环由 `execution_outcome` 独立表达，不用任一字段覆盖另一字段。
- API 契约同步扩展：Session 列表项与树根返回 `runtimeKey`，列表项返回 `executionOutcome`，Agent 节点返回 `executionOutcome/endReason`，Agent 证据字段返回 `agentDefinitionHash/definitionSource`，事件按需返回 `objectRevision/definitionHash/fileReadHash/readComplete/relationConfidence`。状态字段使用封闭 `Literal`，未记录的可选证据通过 `exclude_if` 不序列化。
- `runtime_version` 继续落在 `session_families.cli_version`，`parser_version` 继续按 runtime 存在 `source_records`，模型证据继续用 `agents.model`（实际上报）与 `agents.requested_model`（请求别名）分列，不新增重复列。
- 文件读取证据本轮只落 `file_read_hash` 与 `read_complete`；路径与范围属于 M9-02 的 parser 证据，知识文档的 `source_path` 归 M9-05，不在 0016 额外造列。
- [05 §3.1–§3.2](../../../../plans/fullstack-design/05-api-design.md) 同步记录这些 DTO 字段与封闭集合，避免契约只活在代码里。
- 本 issue 只建立数据与 DTO 契约：不解析新证据，所有新字段在归一化补写前保持 `legacy_unknown` 或 NULL。

## Alternatives considered

- **新开一张 evidence 表**：这些字段与 Session/Agent/事件一一对应，拆表只会增加 join 和一致性窗口；拒绝。
- **复用 `session_families.status` 表达执行闭环**：解析健康与执行完成是两条独立故障轴，合并后无法区分“文件能解析但子 Agent 没返回”；拒绝。
- **新增 `runtime_version`、`reported_model` 重复列**：`cli_version` 和 `model` 已分别承载运行版本与实际模型，重复列会产生两个真相；拒绝。
- **给所有枚举加数据库 CHECK 约束**：SQLite 需要重建表，MySQL 版本差异大，收益低于在 API 边界校验；本轮用封闭 DTO 校验，迁移保持可重复。
- **证据字段总是返回 null**：前端契约要求“只在存在时返回”，用 Pydantic `exclude_if` 保持响应紧凑；拒绝固定输出 null。

## Consequences

- 在 M9-02 写入真实证据前，所有 Session/Agent 都是 `legacy_unknown`，客户端必须把它当作“未知”而不是“已完成”。
- `relationConfidence` 与文件读取字段目前没有写入方，由 M9-02/M9-03/M9-04 填充；本 issue 只保证列和 DTO 已就位。
- 新增 `runtimeKey`、`executionOutcome` 是 OpenAPI 的破坏性增量；仓库内 Web fixture 已同步，外部客户端升级前需要适配。
- `object_revision` 仍按字符串保存 `tag:` / `digest:` / `unknown`，解析与合法性由 M9-04 收口，本 issue 不提前推断版本。
- 迁移只追加列，不改变现有主键、runtime 身份或归因表；降级会删除这些列并保留其余数据。
