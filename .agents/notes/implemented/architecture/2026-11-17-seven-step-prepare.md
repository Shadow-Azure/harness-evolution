# Agent Note: 七步 prepare、聚类输入与历史 run 适配

Status: implemented

[English](2026-11-17-seven-step-prepare.en.md) | 中文

## Problem

V2 的输入链是「空间 bad case → Session 关联 → 潜在 bad case → 对象归因 → 聚类」。V1 的 prepare 直接从已分析 probe 聚类，既没有版本精确的 Session 关联，也没有潜在筛选与缓存复用；读取侧还是六步键（input/clusters/attribution/severity），且把 probe 当成问题本体。若只改 prepare 而不改读取，新 run 会写一套七步游标、页面却按六步解释；若直接删掉 V1 数据，历史 run 就不可读。同时，重复 prepare、失败重试和 `blocked(attribution)` 恢复必须保持幂等，否则会重复写候选或重复调用引擎。

## Decision

- 状态机统一为七步：`range / sessions / potential / attribution / clusters / iteration / final`，阈值 `1,2,3,4,5,5+M,6+M`，`total = 5 + M + 1`。prepared 固定为 unit 5；`cluster_only` 在 unit 5 直接 `completed`，`iteration/final` 对它是 404。
- prepare 按阶段推进：校验 → `sessions`（共享 matcher 的 `associated_sessions`）→ `potential`（同一 matcher 的 `potential_cases`）→ 候选批量 upsert → `attribution`（`AttributionRunner`）→ 只用 attributed 候选聚类并写 confidence/severity/rank → workspace 与 rounds → `mark_prepared(5)`。每个阶段先完成自己的写事务再推进游标；失败重试从游标处继续。
- 候选唯一键 `(run_id, bad_case_id)` + 单事务批量 upsert；重复 prepare 不会新增候选。归因阶段从候选表重建 included 行，`AttributionRunner` 再用候选 `probe_id` 跳过已完成项，因此 `blocked(attribution)` 重入只补缺口。
- 聚类输入固定为 `evolution_run_candidates.included=true` 且 `probe_reports.conclusion='attributed'` 的 probe/案例；`non_target` 保留归因明细与候选行，但永远不进簇。簇 confidence 按 category 取 `error 0.82 / prompt 0.74 / model 0.66`，severity 用 `min(10, confidence × impact × reportWeight)`，rank 按 severity 降序。
- 读取侧只有一个 `build_step_payload`：range 读 run 快照，sessions/potential 读候选，attribution 读候选与 probe 关联，clusters 读 cluster 快照与成员，iteration/final 读 rounds/final。未到达的 step 返回 `STEP_NOT_READY`；cluster_only 只隐藏 iteration/final。
- 历史 V1 run 以 `attribution_engine='legacy-probe-import'` 识别，**不重写** `progress_unit`：读取时 0/1 保持原值、2–4 视为 prepared 的 5、≥5 加一。V1 的 probe/cluster/round 由同一 builder 的兼容分支映射为七步 DTO；sessions/potential 行由 probe 与 source case 合成，缺可比重放坐标时 `orderState=unknown`，不伪造顺序。
- 七步事件新增 `sessions_linked / potential_computed / attribution_created / attribution_reused`；归因事件每 20 条一条，避免事件表与 SSE 洪泛。

## Alternatives considered

- **保留六步读取、只改 prepare**：新 run 的游标语义与页面状态漂移，且无法表达 sessions/potential；拒绝，读取与写入一起切到七步。
- **给历史 run 做数据迁移重写游标**：会改写不可变历史、需要 backfill 回滚方案，且 V1 数据无法真实还原 V2 的 sessions/potential 行；拒绝，只读投影。
- **prepare 每阶段用独立 job**：当前没有独立重跑 UI，拆 job 会引入新的调度与幂等面；拒绝，保持一个 prepare job、阶段内先写后推进。
- **聚类继续读全部 probe**：会把 non_target 与策略排除行混进簇和 severity；拒绝，repository 只投影 attributed 候选。
- **sessions 步骤为每行计算 potentialCount**：会为分页行重复全量 potential；m10-02 已把该字段从预览移除，读取侧改用候选快照的 included 计数，不在请求时重算匹配。
- **cluster_only 也建 rounds**：会伪造从未执行的迭代；拒绝，unit 5 直接终态。
- **归因重跑重算全部候选**：重复引擎调用并覆盖已完成结论；拒绝，用候选 probe 指针作为完成标记。

## Consequences

- 七步是新的唯一 schema；前端 run 详情、RunCard 与事件日志在同一 PR 内切到七个 key，旧六步 DTO 不再对外发布。
- 历史 run 的 sessions/potential 行是兼容合成：`title` 可能为空、`orderState` 可能为 `unknown`、触发点可能缺失；它们只用于解释历史，不应被当作新的精确匹配证据。
- `prepare` 仍是单 job；聚类、workspace 与 rounds 在同一 job 内顺序执行，失败时靠游标与候选/probe 指针恢复，而不是阶段级 job 重试。
- `EvolutionRunStats` 改为 `sessions/versionUnresolvedSessions/badCases/potential/attributed/reused/clusters/byCategory`；历史 run 由旧 `probes/usedProbes/byAttributeType` 兼容合成。
- `rule-v1` 仍是占位规则，severity 与簇描述是占位口径；真实聚类与引擎升级留给 M12，本 Note 只固定输入边界与 DTO 形状。
