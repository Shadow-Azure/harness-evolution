# Agent Note: 多归因分页读取与深链详情

Status: implemented

[English](2026-11-17-attribution-read-api.en.md) | 中文

## Problem

一个 bad case 可以在 `bad_case_analysis` 关联多条 `probe_reports`，但现有 API 只暴露一条内联 `analysis` 与 probe 读端点，错误详情无法分页列出对象·版本归因，也无法用 `at` 深链恢复单条结论。直接复用 `ProbeReport` 会把 probe 重新暴露成主产品概念；按关联行数展示又会把「三条同对象归因」误报成三个对象版本。读取还必须先确认 case 属于当前空间，跨 case 的 attributionId 不能泄露。

## Decision

- 新增 `GET /api/workspaces/{wid}/bad-cases/{badCaseId}/attributions?page=&pageSize=` 与 `.../attributions/{attributionId}`，挂在既有 `problems.py` workspace router 上，复用 `require_workspace_role(viewer)`。列表按 `probe_reports.updated_at DESC, probe_id DESC` 稳定排序，`pageSize` 默认 2、范围 1..50；`total` 只数能投影成 `AttributionItem` 的关联行（inner join probe），与「对象·版本数」分开。
- case 是否存在由 `bad_cases.workspace_id` 的空间条件判定，先于任何归因读取：未知或跨空间 case → `404 BAD_CASE_NOT_FOUND`；attributionId 不在该 case 的关联里 → `404 ATTRIBUTION_NOT_FOUND`。attributionId 直接映射 `probe_id`。
- `BadCase` 增加 `attributionCount` 与 `hasAttribution`，口径固定为 06 §4.2.1 的 distinct `(probe_type, probe_object, object_version)`；在 `service/bad_cases` 的外部读边界由快照内的 analysis/probe 行计算，不新增列、不额外查询。V1 内联 `analysis` 在兼容期保留，V3 再退役，避免与 m11-02 前端切换同时破坏旧页面；条件见 [compatibility](../../../../docs/compatibility.md)。
- `AttributionDetail` 在 item 基础上带 `reason`/`reasoning`/`policyVersion`/`attributionEngine`/`triggerCompare`，并按 issue 要求附固定文案的 `warnings`。`runId` 优先 `last_reused_run_id`，`isCached = last_reused_run_id` 存在；`versionState` 只按是否 pin 了对象版本得 `exact|unknown`。
- `triggerCompare` 取该 probe 最近一次关联的候选：两侧都有 `triggered_at` 时比时间；否则按 `(tree_index, event_index)` 字典序；候选 `order_state=unknown` 或缺坐标 → `unknown`，永远不冒充「之后」。候选的 `order_state` 是 prepare 的权威比较状态，服务层只做同口径的展示推导。
- 触发点证据缺口以固定 code/message 暴露：`ATTRIBUTION_VERSION_UNKNOWN`、`ATTRIBUTION_TRIGGER_UNKNOWN`、`ATTRIBUTION_LEGACY_IMPORT`、`ATTRIBUTION_RUN_UNKNOWN`；文案不插入外部字段，避免漂移数据从警告通道泄露内容。
- 兼容面不动：`/api/bad-cases/{id}/analysis`、`/api/sessions/{sid}/probes`、`/api/probes/{id}` 继续读同一批表；`/probes/{id}` 的 `probeId` 仍是 attributionId 的兼容别名。

## Alternatives considered

- **直接返回 `ProbeReport` 当归因**：会把 probe 重新抬成产品概念，且缺少 `conclusion`/`isCached`/`triggerCompare`；拒绝。
- **用关联行数当 `attributionCount`**：同一对象版本多次复用时会被算成多条对象归因，违反 06 §4.2.1；拒绝。
- **`total` 包含 `probe_id IS NULL` 的 V1 兼容行**：这些行无法投影成 attributionId，分页与总数会互相矛盾；拒绝，仅内连接可达行。
- **仅按时间推导 triggerCompare**：候选允许坐标比较（无 `triggered_at` 时），只比时间会把可比较的证据降级成 unknown；拒绝。
- **现在就删掉 `BadCase.analysis`**：m11-02 前端尚未切换，会同时破坏错误详情；拒绝，留到 V3 兼容退役。
- **为归因另建表/另建 ID**：切断 `probe_id` 与缓存、簇成员和旧 probe 读端点的兼容链；拒绝。

## Consequences

文件报告采用基于 Session、选定对象身份与版本、bad case ID 的确定性摘要，供冻结的写入脚本复核。读取端使用库内完整的 `probe_id`，以便历史复合 ID 仍能定位到原报告。

- m11-02 可以直接按 case 分页取归因并用 `at` 恢复详情；列表与详情共用同一 `probe_id`。
- `attributionCount` 仍是查询时聚合，不随缓存命中或复用次数变化；关联行数只影响分页 `total`。
- 历史行没有对象版本时，详情明确给出 `versionState=unknown` 与 `ATTRIBUTION_VERSION_UNKNOWN`，客户端不能把它描述成版本精确命中。
- `BadCase` 暂时同时带内联 `analysis` 与计数；V3 退役旧字段时只需删字段、不改读取口径。
- 新增 `ATTRIBUTION_NOT_FOUND` 错误码；跨 case 与跨空间都返回 404，不泄露存在性。
