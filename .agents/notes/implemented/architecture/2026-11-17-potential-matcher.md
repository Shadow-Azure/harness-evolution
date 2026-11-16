# Agent Note: PotentialMatcher 与三段预览

Status: implemented

[English](2026-11-17-potential-matcher.en.md) | 中文

## Problem

向导第 2–4 步、未来的 run prepare 与对象总览都要回答同一组问题：对象在哪些 Session 出现、哪些 bad case 是潜在、哪些归因能复用缓存。如果三处各写一套查询与策略，Session 计数、版本口径和策略排除会漂移，且「潜在为 0」与「没有关联 Session」两个空态无法稳定区分。M9 已把对象事件、版本与触发点坐标写入 `agent_events`，但 knowledge 事件只保证 `document_revision`；预览又必须只读，不能顺手执行归因。需要一个只做读取、可被三条路径共用、并把知识对象与坐标比较放进同一切片的实现。

## Decision

- 单一实现：`PotentialMatcher` 住在 `service/evolution/potential.py`，独占 `associated_sessions`、`potential_cases`、`attribution_preview`；`db/crud/potential.py` 只提供分块批量读（窗口 case、session 元数据、对象事件、agents、锚点事件、cache key、non_target 计数），不做 per-case 查询。三段预览服务只做条件归一化、分页与 DTO 映射，不复制策略判断。
- 对象类型：`EvolutionTargetWrite`、target record 与 target DTO 扩为 `skill|agent|knowledge`；`bad_cases.object_type` 与首版归因引擎的 `probe_type` 仍只有 `skill|agent`。knowledge target 走既有 target CRUD，向导目录暂不展示（没有选择器），m10-04 再接 run。
- 对象进入点：`kind` 映射 `object_type`（skill/agent/knowledge），要求 `name == target.name` 且 `object_version == resolved version`；按 `triggered_at` 优先、缺失用 `(tree_index, event_index)` 取最早。版本为空的 Session 只进 `versionUnresolved`，不按名称猜测，也不拿 knowledge 的 `document_revision` 代替版本。
- Session 分区：`reported = associated + versionUnresolved + skipped + pending`，五项互不重叠；`pending` 是没有 `session_families` 行的上报根。第 2 步只列 `associated`，其 `potentialCount` 用默认策略计算。
- 策略：default 固定 `(object_name == target.name AND bad_case_type='self') OR (case_trigger > object_enter)`，携带任一开关 → `422 POLICY_INVALID`；custom 必须给全三开关且至少启用一条匹配规则，先取启用规则的并集，再按 `sameObjectOnly` 过滤。`sameObjectOnly` 只比较 `object_name == target.name`，因为 `bad_cases.object_type` 没有 `knowledge`。命中原因封闭集合为 `self_report|after_object|both|policy_excluded|order_unknown`，排除行只进 `byReason`，不进 `items`。
- 锚点与比较：bad case 锚点按 06 §7.4；skill 取上报 agent 的最后一次同名触发，`discovery+agent` 取父节点 `tool_use_id` 匹配的调用事件，锚点缺失退化为上报 agent 出生点（主 agent 用 session `started_at`，子 agent 用父节点事件）。上报 agent 本身无法解析时保持 `unknown`，不降级到主 agent 猜测位置。双方 `triggered_at` 都非空按时间严格大于，否则按 `(tree_index, event_index)` 字典序；坐标不全 → `order_unknown` 且不满足「之后」。
- 窗口与缓存：按 `bad_cases.created_at` 的 Asia/Shanghai 日边界，无 `from/to` 默认最近 90 天，`from > to` 或超过 366 天 → `422 WINDOW_INVALID`。归因预览只查既有 cache key，键按 `policy_version=v1` 与归因引擎 `rule-v1` 计算；`cacheEnabled=false` 时 `reused=0`；`nonTargetKnown` 是该对象·版本历史 `conclusion='non_target'` 的去重 case 数。
- API：三条 `POST /api/workspaces/{wid}/evolution/preview/{sessions,potential,attribution}` 最低 `viewer`；target 必须在空间内 enabled（否则 `409 TARGET_NOT_CONFIGURED`），无关联 Session（三段）→ `409 NO_ASSOCIATED_SESSIONS`，潜在为 0（潜在与归因段）→ `409 NO_POTENTIAL_MATCHED`。`engineKey` 只做注册校验（`422 ENGINE_INVALID`），预览不执行引擎。三段都只读，不写 `probe_reports`、`bad_case_analysis` 或 `evolution_run_candidates`。

## Alternatives considered

- **每个端点各写查询与策略**：三处计数必然漂移，且无法保证向导、run、总览同一口径；拒绝，改为单一 matcher + 批量 repository。
- **按名称或 `document_revision` 猜版本**：会把「同名不同版本」误算成关联，也会让 knowledge 绕过统一版本口径；拒绝，版本为空只进 `versionUnresolved`。
- **预览时顺手执行归因并写缓存**：会让「预览」产生副作用，破坏只读承诺与缓存审计；拒绝，只按既有 key 计数。
- **把 knowledge 直接加进向导目录**：本切片没有 UI 选择器，目录加项会暴露不可用入口；拒绝，target CRUD 支持、目录暂不展示。
- **上报 agent 缺失时降级到主 agent**：能凑出一个顺序，但会把未知位置伪装成确定结论；拒绝，保持 `unknown`。
- **为预览另建候选/快照表**：候选是 run 级事实，预览没有 run，提前落库会制造无主行；拒绝，m10-04 再由 prepare 写 `evolution_run_candidates`。

## Consequences

- m10-04 的 run prepare 与未来总览必须构造同一个 `MatchCondition` 并调用 `PotentialMatcher`，不得复制策略或坐标逻辑。
- knowledge 关联依赖 `agent_events.object_version`；当前 M9 parser 只保证 `document_revision`，所以真实 knowledge 事件在补版本前通常只会进 `versionUnresolved`。这是已知限制，不是名称级回退的理由。
- policy 语义版本固定 `v1`；换归因引擎或改缓存键组成时，需要同时调整预览的 `ATTRIBUTION_ENGINE` 与迁移口径。
- `sameObjectOnly` 只按名称过滤；若未来 `bad_cases.object_type` 扩为 knowledge，需要重新评估是否把类型纳入同一对象判定。
- 三段预览无 UI 改动；前端向导、目录与 target 表单仍只展示 skill/agent，knowledge 的 run 接线留给 m10-04。
