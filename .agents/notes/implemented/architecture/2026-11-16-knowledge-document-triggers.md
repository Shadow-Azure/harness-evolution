# Agent Note: 知识库文档触发点识别

Status: implemented

[English](2026-11-16-knowledge-document-triggers.en.md) | 中文

## Problem

M9-01/M9-02/M9-04 已经把 Skill、Agent、Workflow 触发、对象 revision 和触发坐标写进 `agent_events`，但知识库使用完全不可见：普通 `Read`、知识搜索与 MCP retrieval 都不产生事件，`kind` 只有 `skill|agent|workflow`。于是归因与自进化看不到“这个 Session 读过哪些知识文档”，也无法把文档版本纳入证据链。若把每个 `Read` 都当知识触发，源码阅读会污染证据；若把文档正文或检索 chunk 落库，又违反轨迹明细不落库的隐私边界。

## Decision

- 事件 `kind` 增加 `knowledge`，与 Session API 的 `SessionEvent` 同批扩展；`bad_cases.object_type` 与 `evolution_targets.object_type` 保持 `skill|agent`，知识事件暂不成为可进化对象。
- 知识根是工作空间配置，存在 `workspaces.knowledge_roots` JSON 字符串数组：必须是绝对路径且不能是文件系统根 `/`，每空间最多 20 条、每条 ≤512 字符，拒绝 `..` 与 NUL；经现有 `PUT /api/workspaces/{wid}` 的 `knowledgeRoots` 由空间管理员写入，写入前归一化为正斜杠、去尾斜杠并去重。JSON 列不设 server default，`NULL` 与 `[]` 等价。`GET /api/workspaces` 只对空间管理员与全局管理员回读真实路径，member/viewer 得到 `[]`。
- 普通 `Read` 只有路径命中知识根才生成事件：先把路径规范化（反斜杠、重复斜杠、尾斜杠）再按最长前缀、段边界匹配（`/kb` 不匹配 `/kb2`），`Edit`/`Bash` 永不生成；文档身份为 `doc:<sha256(规范化根相对路径)[:32]>`，`retrieval_kind=file_read`，`retrieval_scope=命中根`，`source_path` 存规范化路径并截断到 1024。相对路径不匹配、不解析 cwd。
- MCP 只认显式白名单工具名：`mcp__knowledge__search`、`mcp__knowledge__retrieve`、`mcp__knowledge-base__search`、`mcp__knowledge_base__search`、`mcp__kb__search`、`mcp__kb__retrieve`；不做“名字里带 knowledge”的模糊匹配。每个返回文档一条事件，`retrieval_kind` 区分 `mcp_search/mcp_retrieve`，`retrieval_scope` 取 Provider collection，缺失时用 adapter 默认 scope。
- 迁移 `0019` 在同一次变更里给 `agent_events` 加 `document_id/document_revision/source_path/retrieval_kind/retrieval_scope`（512，容纳 512 配置上限）与 `(agent_id, kind, document_id)` 索引，并给 `workspaces` 加 `knowledge_roots`。只存 id、revision、path、kind、scope 与 hash，文档正文、chunk、MCP 原始响应不落库。
- 重放时按根会话关联的 `bad_cases.workspace_id` 取所有上报空间的 roots 并集；并集只做去重归一化（`merge_knowledge_roots`），不套每空间 20 条写侧上限；无 bad case 的本地根为空，`bad_cases` 表缺失时降级为空 roots 而不是整根失败。`parser_version` 4 → 5，`event_index` 在 finalize 按 `(line_no, event_index)` 稳定重排，结果到达顺序不影响坐标。
- 空间管理员修改 roots 且集合实际变化时，该空间上报根对应的 `source_records.parser_version` 置 NULL，下一次 sync/replay 重算；roots 未变（含仅顺序变化）不触发。这样“先导入会话、后配置知识根”的顺序也能补齐证据。
- `document_revision` 保留 Provider 原始 revision（文件读为 `digest:<sha256>`，partial 为 `unknown`）；`object_revision` 走共享封闭词汇：文件读 `digest:<sha256>` / `unknown`，MCP 为 `provider:<原始 revision>` / `unknown`。两个字段语义不同，不再无条件同值。

## Alternatives considered

- **把知识库做成可进化对象**：`object_type=knowledge` 会要求 target 配置、PotentialMatcher 与归因三态同切片落地，本 issue 只交付证据，提前扩枚举会写入下游查不到的取值；拒绝，留在 M10 之后单独切片。
- **知识根放独立表或环境变量**：独立表要新增管理端点与迁移，环境变量无法按空间区分；工作空间已有配置通道和权限模型，用 JSON 列复用 `PUT` 是最小改动；拒绝前两者。
- **按 MCP 工具名前缀或子串推断知识工具**：不同 Provider 的命名没有统一约定，模糊匹配会把无关 MCP 调用误判成知识触发；拒绝，白名单显式列出六个已确认工具名。
- **重放时只取主上报空间的 roots**：同一根会话可能被多个空间上报，各自配置不同知识根，只取一个会漏证据；拒绝，取所有上报空间的并集。查询层按空间裁剪留到 M10。
- **并集也套每空间 20 条上限**：一个纯配置组合（两个空间各 11 条根）就会让整根重放失败，且错误码不指向配置；拒绝，读侧用独立 `merge_knowledge_roots`（去重、忽略非法项、不设数量上限），写侧仍保留 20 条。
- **允许 `/` 作为知识根**：它等价于“全盘 Read 皆知识”，会把源码、配置与 `.env` 路径写入证据并随共享根外溢；拒绝，校验层返回 `too_broad`。
- **成员读接口也返回知识根**：roots 是绝对主机路径，属于部署拓扑；普通成员无需知道，收紧为零成本；拒绝公开，member/viewer 返回 `[]`。
- **partial read 也给出 digest revision**：不完整读取只覆盖文件片段，用它当文档 revision 会让不同片段产生伪版本；拒绝，显式记 `unknown`，由完整读取或 Provider revision 补齐。
- **把 `Read` 的内容或检索 chunk 存进事件**：违反轨迹明细不落库的隐私边界，也让事件表体积不可控；拒绝，只存身份、路径、版本与 hash。

## Consequences

- 未配置知识根的空间没有知识事件；配置 roots 后，服务会把该空间上报根的 parser cursor 置 NULL，下一次 sync 或 `pnpm data:replay:sessions` 即可补齐（parser 5 只影响 `claude-code`）。
- 事件表新增五个可空列与一个索引，旧行读 `NULL`；Session DTO 新字段只在存在时返回，旧客户端可忽略。
- `GET /api/workspaces` 与 `PUT /api/workspaces/{wid}` 的响应新增 `knowledgeRoots`；非法配置返回 `422 KNOWLEDGE_ROOTS_INVALID`，details 只带稳定 reason，不回显路径。
- 归一化现在依赖 `bad_cases` 读取空间知识根：问题侧表缺失时按空 roots 降级，replay 不会因此整根失败，但这些会话没有知识证据。
- 同一根会话被多个空间上报时，roots 取并集，其他空间的成员能看到本空间配置根下的 `sourcePath` 与 `retrievalScope`（路径与文档存在性，不含正文）；按空间裁剪留到 M10。
- `agent_tree` 的父工具 bookkeeping 跳过 `kind=knowledge`，所以知识调用不再参与 `DUPLICATE_TOOL_USE_ID` 诊断；这是一次检索多文档必须的豁免。
- 前端没有 knowledge 专属样式、图例或 Admin roots 输入：事件按通用 pill 渲染，配置只能用 API 完成。产品化（配色、图例、表单）另开 issue，不在本证据层切片。
- 知识事件目前只是归因证据，还不能被 PotentialMatcher 或 target 配置选中；把它升级为可进化对象需要新的 `object_type` 切片与查询层空间过滤。
