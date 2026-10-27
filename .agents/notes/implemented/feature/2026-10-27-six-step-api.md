# Agent Note: 六步只读端点与后端直出的状态语义

Status: implemented

[English](2026-10-27-six-step-api.en.md) | 中文

## Problem

m5-06 要在不复制设计事实的前提下落地 05 §3.6 的六个只读端点：运行详情页每一步的内容各不相同，但状态判断（done/active/pending、clickable、未到达 404）必须只有一个权威来源；同时执行引擎尚未落地，写路径只有 m5-01 的占位 prepare，读端点必须对"尚未真正运行过的 run"也给出明确行为。

## Decision

- readiness 唯一来自 m5-01 的 unit 游标状态机：`EvolutionStageService` 用 `step_states` 推导每步 status，`clickable = status != "pending"` 由后端直出（R4），六个端点共享同一 `build_step_payload(run, clusters, key)`，只按 key 组装 DTO，不复制任何状态逻辑。
- 分数列只读不重算：`confidence/impact/severity/rank` 直接读 `probe_clusters` 列（07 §5.10"接口只读这些列，不再占位计算"），`probeCount/reportCount` 是读时关联计数，排序按落库 severity 降序、未排序簇垫底。
- 404 语义：未知 run 返回 `RUN_NOT_FOUND`；pending 步返回 `STEP_NOT_READY`（details 带 key）；`preparing` 的 `input` 返回准备态——`status=active` 加条件快照、零值 hits、空 rows，不是 404（05 §3.6）。
- blocked 不另造游标：被阻塞 run 的 done 步照常可读，active 步（如 iteration）带"第 x/y 轮"detail 可读，后续步 404；cluster_only run 以终态停在 unit 2，attribution/severity/iteration/final 天然 pending→404，clusters 以 null confidence/severity 呈现（05 §4.12 由状态机自然满足，不加 mode 特判）。
- 六组 fixture 按 05 §3.6.1 形状与六份响应快照一起落在 `apps/api/tests/m5-06-six-step-api/`（issue 验证命令目录），不进根 `fixtures/`——那里是 seed 语料的 home。
- 事实同步：真实 prepare 编排与 `ENGINE_INVALID` 的引擎注册表属于引擎切片 m5-09–m5-11，不是本切片；m5-05 note 与占位 handler 的陈述已随本切片改为引擎切片口径。

## Alternatives considered

- 一个 `GET /steps/{key}` 动态路由：05 §3.6 已把六步拆成六个独立端点，动态 key 会把响应形状判别推迟到运行时，OpenAPI 也无法按端点给形状；否。
- 在 stage service 里对空值 confidence/severity 兜底重算：会漂移出第二套口径并与写路径竞争；否。
- 为 cluster_only 增加 mode 特判强制 404：终态下状态机不给 active 步，四步天然 pending→404，特判属于复制状态逻辑；否。

## Consequences

- 运行详情 UI（m5-07）直接消费 status/clickable 与各步 payload，前端不再推算步骤状态，深链 `step=` 直接查表。
- 六份快照成为执行引擎（m5-09–m5-11）的对照基准：引擎写库后的读形状必须与快照一致，偏离即视为引擎破坏读契约。
- `input` 在 preparing 的零值 hits 是明确空态而非错误；迭代 detail 只在 active 时出现，done 步 `detail` 恒为 null。
- run 级 readiness 依赖 `list_clusters` 计数 M；若未来允许簇软删或跨 run 聚类，需要重新校对 `total_units` 口径。
