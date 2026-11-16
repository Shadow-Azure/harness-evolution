# Agent Note: 对象 revision 解析与触发坐标

Status: implemented

[English](2026-11-16-object-revision-trigger-coordinates.en.md) | 中文

## Problem

真实 Claude Code 会话并不总有语义版本：Skill 列表可能只给名称、内容摘要与 16 位不透明 digest，Skill body 要靠 `isMeta + sourceToolUseID` 注入才能看到；subagent 的定义 body 则藏在 `prompt_snapshot.systemPrompt[0]`。M9-01/M9-02 已经把这些证据解析成 hash，但事件表只存了 `definition_hash`，没有对象 revision、`object_version`、`triggered_at` 或稳定的 `tree_index`。结果是后续 PotentialMatcher 只能比较 targetVersion 或名称，既会漏掉“只有 body/digest 的对象”，也无法按“对象进入点早于 bad case 触发点”做稳定排序。

## Decision

- 迁移 `0018` 只加坐标列：`agents.tree_index`（非空、默认 0）、`agent_events.triggered_at`、`agent_events.object_version`，并补 `(agent_id, triggered_at)` 与 `(agent_id, kind, name, object_version)` 索引。排在 `0017_per_report_session_source` 之后，沿用 0016 的列存在性守卫，MySQL 部分 DDL 失败后可重跑；SQLite 降级用 batch 模式。
- 对象 revision 只有三种形态：`tag:<tag>`、`digest:<sha256>`、`unknown`。显式 `tag` 或 `version/skillVersion/agentVersion` 元数据产生 tag，tag 永远优先；没有 tag 时才使用 body 或 listing digest；三者都没有就是显式 `unknown`，不从名称、描述或默认分支猜测。
- Skill revision 的 digest 绑定 `source_path + 归一化 body hash`，而不是只有 body hash：同一个 Skill body 复制到不同路径会被视为不同对象；同一路径同一 body 跨会话、跨任务稳定。`definition_hash` 继续只表达 body hash，两者不互相覆盖。
- Agent revision 由 `agentType + isBuiltIn + systemPrompt[0] body hash` 组合成 digest，内置 agent 没有 body 但仍保留类型与 builtin 标记；非内置且没有 body 时为 `unknown`。父 `kind=agent` 事件在树组装阶段拿到子 transcript 的 revision，父调用自身带 tag 时仍以 tag 为准。
- `skill_listing` 的 16 位 digest 只作为 fallback：支持 `digests` 映射/数组、`skills[]` 与单名 `digest` 等已观测形状；不反推算法，有 body 时绝不使用 listing digest。
- `triggered_at` 取触发 `tool_use` 所在 assistant 记录的 `timestamp`，统一转 Asia/Shanghai；缺时间就留 NULL。`tree_index` 在树组装后按 DFS 先序（父先于子，兄弟按 `sort_key`）一次赋值，工作流与合成节点也占一个坐标。
- `attributionSkill` 只作为补充解析证据保留，不合成 `agent_events`：显式 `Skill` 调用才是触发事件；没有显式调用时宁可没有事件，也不把归因标记冒充触发点。原始载荷仍在 `trajectory_payloads`，不另造无设计的列。
- `ClaudeCodeTraceParser.parser_version` 升到 4，只重放 claude-code；同一会话的旧 `source_records` 由下一次同步或 `pnpm data:replay:sessions` 补齐。Skill 定义 hash 的映射从 `agent_tree` 下移到 parser 的 `finalize`，避免两个写入方。

## Alternatives considered

- **只存 body hash 作为 revision**：同一个定义 body 出现在不同 Skill 路径时会被错误合并，无法满足“path + body hash”的对象身份。
- **把 listing digest 当作主键**：16 位 digest 的算法尚未确认，用它做主键会把不可验证的摘要带进 Session 关联和缓存键；只允许作 fallback。
- **把 attributionSkill 写成 synthetic skill 事件**：它没有稳定的 tool-use 身份，会污染触发坐标和“显式触发”口径；拒绝。
- **在读取 API 时临时计算 tree_index/triggered_at**：读取路径拿不到完整的父子与 `sort_key`，而且每次读取都要重算；持久化后重放一次即可稳定比较。
- **给 agent_events 增加 source_path 列**：M9-02 的检视已确认 path/range 暂留 parser 证据，知识文档 `source_path` 由 M9-05 统一定义；本轮不提前造列。
- **在迁移里用 SQL 回填 tree_index**：DFS 依赖组装后的父子关系和 `sort_key`，迁移无法可靠计算；存量先保持 0，重放补齐。

## Consequences

- 未重放的存量 Session：`tree_index` 全为 0、`triggered_at/object_version` 为 NULL。消费方必须把“未重放”视为坐标未知，不能把 0 当成“主 Agent 的稳定序”，也不能用 NULL 做“之后”判断。
- 事件 revision 现在覆盖所有显式触发；`agent` 事件缺少子 transcript 时仍是 `unknown`，不会从 `subagent_type` 名称推断定义版本。
- listing digest 的算法依旧未确认，当前只保存、不用于匹配；确认后再由 M10 决定是否升级为可比较身份。
- `attributionSkill` 不落独立列；若 M10 需要按归因标记做统计，必须先补设计再迁移，不能直接复用 `agent_events`。
- `object_version` 只接受显式元数据；名称相同但版本缺失的对象仍会在潜在匹配阶段被跳过并计数，这是有意的安全边界。
