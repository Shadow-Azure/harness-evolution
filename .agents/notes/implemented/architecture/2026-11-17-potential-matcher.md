# Agent Note: PotentialMatcher 与三段预览

Status: implemented

[English](2026-11-17-potential-matcher.en.md) | 中文

## Problem

后台绑定、向导与 Run 都需要判断完整 Session 树中是否出现对象。生产轨迹可能缺少版本，或记录了与本次分析原文不同的历史版本。三条路径需要相同的入选口径，同时保留原始证据和报告所用的快照身份。

## Decision

- 单一实现：`PotentialMatcher` 住在 `service/evolution/potential.py`，独占 `associated_sessions`、`potential_cases`、`attribution_preview`；`db/crud/potential.py` 只提供分块批量读（窗口 case、session 元数据、对象事件、agents、锚点事件、cache key、non_target 计数），不做 per-case 查询。三段预览 service 只做条件归一化、分页与 DTO 映射，不复制策略判断。
- Session 按归一化事件的对象类型和名称关联。缺少调用事件时，Agent 节点的类型（缺失时用名称）或节点的 Skill 名也可作为出现证据。相同名称的不同类型分别匹配。
- 上下文保留观测到的版本和坐标；选定的目标 revision 固定原文、报告与缓存范围。节点级证据引用节点本身。总览按历史版本分组时，单独限定观测 revision，避免把同一条 Badcase 计入每个历史版本。
- 对象类型：`EvolutionTargetWrite`、target record 与 target DTO 扩为 `skill|agent|knowledge`；`bad_cases.object_type` 仍只有 `skill|agent`，`probe_reports.probe_type` 在 m10-03 写入知识归因前允许 knowledge。knowledge target 的 `defaultRef` 接受 revision 形式；创建/更新跳过 git `ls-remote`，`versions` 返回空列表 + `defaultRef`。向导 catalog 与 target 表单暂不展示 knowledge（无选择器），run 启动也仍限 skill/agent；可配置 ≠ 可启动，m10-04 接 run。
- 新关联分区为已出现、已跳过、待补轨迹；兼容字段 `versionUnresolved` 为零。第二步仅分页展示关联 Session，空态沿用 409 和分区计数。
- 策略：default 固定 `(object_name == target.name AND bad_case_type='self') OR (case_trigger > object_enter)`，携带任一开关 → `422 POLICY_INVALID`；custom 必须给全三开关且至少启用一条匹配规则，先取启用规则的并集，再按 `sameObjectOnly` 过滤。`self` 与 `sameObjectOnly` 都只比较 `object_name`，不比较 `bad_cases.object_type` 或 `object_version`；同名 skill/agent 与跨版本 self 会被纳入。命中原因封闭集合为 `self_report|after_object|both|policy_excluded|order_unknown`，排除行只进 `byReason`，不进 `items`。
- 锚点与比较：bad case 锚点按 06 §7.4；skill 取上报 agent 的最后一次同名触发，`discovery+agent` 取父节点 `tool_use_id` 匹配的调用事件，锚点缺失退化为上报 agent 出生点（主 agent 用 session `started_at`，子 agent 用父节点事件）。上报 agent 为空串按缺失回退主 agent；非空 agent 必须属于本 Session，父关系 unresolved 的 subagent 不借用 session start，而是保持 `unknown`。双方 `triggered_at` 都非空按时间严格大于，否则按 `(tree_index, event_index)` 字典序；坐标不全 → `order_unknown` 且不满足「之后」。取最早对象进入点使用同一口径（双方都有时间才比时间），混合时间戳不会把“有时间但更晚”的事件误当最早。
- 窗口与缓存：按 `bad_cases.created_at` 的 Asia/Shanghai 日边界，无 `from/to` 默认最近 90 天，`from > to` 或超过 366 天 → `422 WINDOW_INVALID`。归因预览不接收 `engineKey`、也不执行引擎；绑定包模式按 `bad_case_analysis` 取每例 `analyzed_at` 最新的完成报告，并按 `attribution_skill_name` 汇总 `bySkill`，`missing=potential-reused`；`cacheEnabled=false` 时 `reused=0`、`fresh=potential`、`missing=0`。legacy rule 模式才查既有 cache key（`targetRevision`、`policy_version=v1`、`rule-v1`）。`nonTargetKnown` 按 `targetVersion`/`targetRevision` 查该对象历史 `conclusion='non_target'` 去重 case 数，是参考值、可与 `reused` 重叠。
- API：三条 `POST /api/workspaces/{wid}/evolution/preview/{sessions,potential,attribution}` 最低 `viewer`；target 必须在空间内 enabled（否则 `409 TARGET_NOT_CONFIGURED`），无关联 Session（三段）→ `409 NO_ASSOCIATED_SESSIONS` + summary，潜在为 0（潜在与归因段）→ `409 NO_POTENTIAL_MATCHED`。三段都只读，不写 `probe_reports`、`bad_case_analysis` 或 `evolution_run_candidates`。

## Alternatives considered

- 仅纳入与快照版本一致的对象会排除有明确调用证据的历史轨迹，导致 Badcase 无法分析。
- 用选定版本填补历史轨迹会伪造证据。报告与缓存记录实际选用的原文，轨迹版本未知时保留未知。
- **knowledge target 继续走 git 校验**：知识文档不一定是 git 对象，管理员会被迫编一个能过 `ls-remote` 的仓库；拒绝，knowledge 跳过 git 校验并返回空版本列表。
- **每个端点各写查询与策略**：三处计数必然漂移，且无法保证向导、run、总览同一口径；拒绝，改为单一 matcher + 批量 repository。
- **第 2 步 409 不带 summary，或改成 200 空页**：前者丢掉 `versionUnresolved` 的解释力，后者与既有 409 契约冲突；拒绝，保留 409 并把五数放进 `details.summary`。
- **预览保留 `engineKey`**：它校验的是 run engine 注册表，缓存键却固定归因引擎，语义含混；拒绝，删除字段，预览不执行引擎。
- **预览为 4 行 Session 计算全量 potential**：为封面搬整个图书馆；拒绝，第 2 步只做关联，`potentialCount` 留给 m10-04 的 run 步骤。
- **self/sameObjectOnly 比较类型或版本**：产品尚未确认收紧，且 06 §7.5 写的是名称-only；拒绝，保持名称-only 并在文档/测试锁定。
- **为预览另建候选/快照表**：候选是 run 级事实，预览没有 run，提前落库会制造无主行；拒绝，m10-04 再由 prepare 写 `evolution_run_candidates`。

## Consequences

- m10-04 的 run prepare 与未来总览必须构造同一个 `MatchCondition`（含 `target_revision`）并调用 `PotentialMatcher`，不得复制 identity、策略或坐标逻辑。
- 历史 Run 的计数按原快照展示；新绑定与向导共用按出现筛选的结果。
- policy 语义版本固定 `v1`；换归因引擎或改缓存键组成时，需要同时调整预览的 `ATTRIBUTION_ENGINE` 与迁移口径。
- `sameObjectOnly` 与 self 只按名称；同名不同类/跨版本会被纳入。若未来 `bad_cases.object_type` 扩为 knowledge 或产品要收紧，需要重新评估并补迁移测试。
- knowledge target 目前只能通过 API 配置和预览，catalog、target 表单与 run 启动仍只支持 skill/agent；选择器与 run 接线留给 m10-04。
- 三段预览与原型必须共用 presence 口径：05/06/07/08 不得再把 Session 关联写成 identity 命中；原型第 4 步的 `attributionSkill` 要随 Run 持久化，Run 详情与第 4 步共用复用/新增/缺报告计数。第 2 步 409 的 `details.summary` 是向导空态的唯一解释来源。
