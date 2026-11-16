# Agent Note: 知识库文档触发点识别

Status: implemented

[English](2026-11-16-knowledge-document-triggers.en.md) | 中文

## Problem

M9-01/M9-02/M9-04 已经把 Skill、Agent、Workflow 触发、对象 revision 和触发坐标写进 `agent_events`，但知识库使用完全不可见：普通 `Read`、知识搜索与 MCP retrieval 都不产生事件，`kind` 只有 `skill|agent|workflow`。于是归因与自进化看不到“这个 Session 读过哪些知识文档”，也无法把文档版本纳入证据链。若把每个 `Read` 都当知识触发，源码阅读会污染证据；若把文档正文或检索 chunk 落库，又违反轨迹明细不落库的隐私边界。

## Decision

- 事件 `kind` 增加 `knowledge`，与 Session API 的 `SessionEvent` 同批扩展；`bad_cases.object_type` 与 `evolution_targets.object_type` 保持 `skill|agent`，知识事件暂不成为可进化对象。
- 知识根是工作空间配置，存在 `workspaces.knowledge_roots` JSON 字符串数组：绝对路径、每空间最多 20 条、每条 ≤512 字符，拒绝 `..` 与 NUL；经现有 `PUT /api/workspaces/{wid}` 的 `knowledgeRoots` 由空间管理员写入，写入前归一化为正斜杠、去尾斜杠并去重。JSON 列不设 server default，`NULL` 与 `[]` 等价。
- 普通 `Read` 只有路径命中知识根才生成事件：按最长前缀、段边界匹配（`/kb` 不匹配 `/kb2`），`Edit`/`Bash` 永不生成；文档身份为 `doc:<sha256(根相对路径)[:32]>`，`retrieval_kind=file_read`，`retrieval_scope=命中根`。
- MCP 只认显式白名单工具名：`mcp__knowledge__search`、`mcp__knowledge__retrieve`、`mcp__knowledge-base__search`、`mcp__knowledge_base__search`、`mcp__kb__search`、`mcp__kb__retrieve`；不做“名字里带 knowledge”的模糊匹配。每个返回文档一条事件，`retrieval_kind` 区分 `mcp_search/mcp_retrieve`，`retrieval_scope` 取 Provider collection，缺失时用 adapter 默认 scope。
- 迁移 `0019` 在同一次变更里给 `agent_events` 加 `document_id/document_revision/source_path/retrieval_kind/retrieval_scope` 与 `(agent_id, kind, document_id)` 索引，并给 `workspaces` 加 `knowledge_roots`。只存 id、revision、path、kind、scope 与 hash，文档正文、chunk、MCP 原始响应不落库。
- 重放时按根会话关联的 `bad_cases.workspace_id` 取所有上报空间的 roots 并集；无 bad case 的本地根为空。`parser_version` 4 → 5，`event_index` 在 finalize 按 `(line_no, event_index)` 稳定重排，结果到达顺序不影响坐标。
- 完整文件读的 `document_revision` 为 `digest:<sha256>`；partial/truncated 读为 `unknown`。`object_revision` 与 `document_revision` 同值。

## Alternatives considered

- **把知识库做成可进化对象**：`object_type=knowledge` 会要求 target 配置、PotentialMatcher 与归因三态同切片落地，本 issue 只交付证据，提前扩枚举会写入下游查不到的取值；拒绝，留在 M10 之后单独切片。
- **知识根放独立表或环境变量**：独立表要新增管理端点与迁移，环境变量无法按空间区分；工作空间已有配置通道和权限模型，用 JSON 列复用 `PUT` 是最小改动；拒绝前两者。
- **按 MCP 工具名前缀或子串推断知识工具**：不同 Provider 的命名没有统一约定，模糊匹配会把无关 MCP 调用误判成知识触发；拒绝，白名单显式列出六个已确认工具名。
- **重放时只取主上报空间的 roots**：同一根会话可能被多个空间上报，各自配置不同知识根，只取一个会漏证据；拒绝，取所有上报空间的并集。查询层按空间裁剪留到 M10。
- **partial read 也给出 digest revision**：不完整读取只覆盖文件片段，用它当文档 revision 会让不同片段产生伪版本；拒绝，显式记 `unknown`，由完整读取或 Provider revision 补齐。
- **把 `Read` 的内容或检索 chunk 存进事件**：违反轨迹明细不落库的隐私边界，也让事件表体积不可控；拒绝，只存身份、路径、版本与 hash。

## Consequences

- 未配置知识根的空间与未重放的存量 Session 没有知识事件；`pnpm data:replay:sessions` 重放后补齐，parser 5 只影响 `claude-code`。
- 事件表新增五个可空列与一个索引，旧行读 `NULL`；Session DTO 新字段只在存在时返回，旧客户端可忽略。
- `GET /api/workspaces` 与 `PUT /api/workspaces/{wid}` 的响应新增 `knowledgeRoots`；非法配置返回 `422 KNOWLEDGE_ROOTS_INVALID`，details 只带稳定 reason，不回显路径。
- 归一化现在依赖 `bad_cases` 读取空间知识根：只有问题侧表就绪的环境才有知识证据，测试中只建内部表的 DB 需显式 bootstrap 外部表。
- 知识事件目前只是归因证据，还不能被 PotentialMatcher 或 target 配置选中；把它升级为可进化对象需要新的 `object_type` 切片与查询层空间过滤。
