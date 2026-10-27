# Agent Note: 六步只读端点与后端直出的状态语义

Status: implemented

[English](2026-10-27-six-step-api.en.md) | 中文

## Problem

m5-06 要在不复制设计事实的前提下落地 05 §3.6 的六个只读端点：运行详情页每一步的内容各不相同，但状态判断（done/active/pending、clickable、未到达 404）必须只有一个权威来源；同时执行引擎尚未落地，写路径只有 m5-01 的占位 prepare，读端点必须对"尚未真正运行过的 run"也给出明确行为。

## Decision

- readiness 唯一来自 m5-01 的 unit 游标状态机：`EvolutionStageService` 用 `step_states` 推导每步 status，`clickable = status != "pending"` 由后端直出（R4），六个端点共享同一 `build_step_payload(run, clusters, key)`，只按 key 组装 DTO，不复制任何状态逻辑。
- 分数列只读不重算：`confidence/impact/severity/rank` 直接读 `probe_clusters` 列（07 §5.10"接口只读这些列，不再占位计算"），`probeCount/reportCount` 是读时关联计数，排序按落库 severity 降序、未排序簇垫底。
- 404 语义：未知 run 返回 `RUN_NOT_FOUND`；pending 步返回 `STEP_NOT_READY`（details 带 key）；`preparing` 的 `input` 返回准备态——`status=active` 加条件快照、零值 hits、空 rows，不是 404（05 §3.6）。
- 终评空态用 `null` 而不是零值：`evolution_finals` 无行时 `StepFinalPayload.verdict/bestVersion/bestScore/initScore` 为 `null`、`metrics` 为 `[]`，`changes` 仍按已接纳轮次给出；"0 分"是有业务含义的数，零值会把"还没出结果"伪装成"终评失败"（05 §3.6）。
- blocked 不另造游标：被阻塞 run 的 done 步照常可读，active 步（如 iteration）带"第 x/y 轮"detail 可读，后续步 404；cluster_only run 不论进行中还是终态，都只答 `input`/`clusters`——`attribution/severity/iteration/final` 由 readiness 入口（`ensure_step_readable` 的 `mode` 参数）按 05 §4.12 一律 404，`step_states` 仍是纯游标状态机；clusters 以 null confidence/severity 呈现。
- 第 0 步 `hits` 按该 run 已落簇的 probe 计数，不按条件重查（05 §3.6、07 §5.10）：读路径只读已落库事实、可审计、不重跑筛选查询；prepare 真接上后补一条"命中 N / 落簇 M"对账测试，留给后续切片，不在本 PR 实现。
- 六组 fixture 按 05 §3.6.1 形状与六份响应快照（外加 active 终评变体 `step-final-active`）一起落在 `apps/api/tests/m5-06-six-step-api/`（issue 验证命令目录），不进根 `fixtures/`——那里是 seed 语料的 home。
- 事实同步：真实 prepare 编排（workspace/ref 校验、筛选、聚类、状态推进）与 `ENGINE_INVALID` 引擎注册表校验由引擎切片 m5-09 认领（m5-09–m5-11 区间内），不是本切片；m5-05 note 与占位 handler 的陈述已随本切片改为引擎切片口径。

## Alternatives considered

- 一个 `GET /steps/{key}` 动态路由：05 §3.6 已把六步拆成六个独立端点，动态 key 会把响应形状判别推迟到运行时，OpenAPI 也无法按端点给形状；否。
- 在 stage service 里对空值 confidence/severity 兜底重算：会漂移出第二套口径并与写路径竞争；否。
- 把 cluster_only 的隐藏规则放进 `step_states`：mode 会混进 R4 想保持纯净的游标状态机，四个 step 还得各自记住 mode；否——改为 readiness 入口按 05 §4.12 拦一道，状态机保持无 mode。
- final 的 active 空态保持零值、把"零值即未出结果"写进契约语义：`0 分` 与"终评失败"同形，m5-07 只能靠 status 区分，误读成本高；否。

## Consequences

- 运行详情 UI（m5-07）直接消费 status/clickable 与各步 payload，前端不再推算步骤状态，深链 `step=` 直接查表。
- 六份 §3.6.1 快照与 active 终评变体成为执行引擎（m5-09–m5-11）的对照基准：引擎写库后的读形状必须与快照一致，偏离即视为引擎破坏读契约。
- `input` 在 preparing 的零值 hits 是明确空态而非错误；final 在 active 且无终评行时四个结论字段为 `null`，m5-07 必须按 status 渲染、不得把 null 当失败；迭代 detail 只在 active 时出现，done 步 `detail` 恒为 null。
- cluster_only 的"一律 404"已由 readiness 守卫兜住，不再依赖"引擎一定把 run 收成终态"这个未来前提；引擎切片接上 prepare 后无需再补 mode 特判。
- run 级 readiness 依赖 `list_clusters` 计数 M；若未来允许簇软删或跨 run 聚类，需要重新校对 `total_units` 口径。
