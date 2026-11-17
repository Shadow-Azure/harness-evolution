# Agent Note: 进化对象总览聚合 API

Status: implemented

[English](2026-11-17-target-overview-api.en.md) | 中文

## Problem

工作空间总览除了 bad case 主视角，还需要从「进化对象」回看：每个对象在当前窗口里出现在哪些 Session、产生了多少潜在 bad case、这些潜在 case 被归因为「是该对象」「非该对象」还是「未分析」。这些数字不能由前端把多个列表拼出来：潜在集合必须与向导、run 使用同一个 matcher，三态必须从同一批归因行去重，趋势要把归因时间与上报时间分开落桶，还要同时支持 skill、agent 与 knowledge revision。任何一条读路径漏掉空间过滤，都会把别的空间的对象、case 或归因混进来。

## Decision

- 新增四个只读端点，全部挂 `require_workspace_role(wid, "viewer")`：`GET /api/workspaces/{wid}/overview/targets`、`/targets/trend`、`/targets/cases`、`/targets/{targetId}/detail`。全部固定路径空间：目标来自该空间的 `evolution_targets`，case 来自该空间的 `bad_cases`，归因还要匹配 `probe_reports.workspace_id`。空间不存在或不可见沿用 `404 WORKSPACE_NOT_FOUND`；目标不存在、已停用或属于别的空间统一 `404 TARGET_NOT_FOUND`。
- 时间窗与 bad case 总览共用 `service/overview/window.py`：`from`/`to` 双边界直接使用，单边界必须带 `range`，都不给默认最近 90 天，`range` 只在参与推导时校验 7/30/90；`from > to`、跨度 >366 天、越界日期返回 `422 WINDOW_INVALID`；趋势的 `grain` 仍是 `day|week|month`，日粒度超过 92 天降级为周。四个目标端点也都接受 `range`，与设计 05 §4.18「四个总览读端点都接受 range」一致。
- 目标版本不是只取 `defaultRef`：先从窗口内已上报 case 的根 Session 中，取该对象 `kind`/`name` 的全部 `agent_events.object_version` 与 `object_revision`，把 `tag:` 前缀去掉后去重，再并上配置的 `defaultRef`，按自然版本号降序排列。每个版本单独构造 `MatchCondition` 调一次 `PotentialMatcher.associated_sessions` 与 `potential_cases`，所以「潜在数与向导/run 同条件一致」是按 `(target, version)` 成立的；对象级 `potential` 是这些版本行之和。
- 一行潜在数据是 `(badCaseId, targetVersion)`，不是去重后的 case。同一 case 可以在同一对象的多个版本、或不同对象下各出现一次；这与 05 §3.10「版本趋势允许同一 bad case 在多个版本各有一条归因」以及原型「同一 bad case 可能同时出现在多个进化对象下」一致。对象列表的 `potential = attributed + nonTarget + unanalyzed`，`evolvable = attributed + unanalyzed`，按 `evolvable DESC, potential DESC, objectName ASC` 排序；detail 用 `distinctCases` 单独给出 case 去重数。
- 三态判定只读 `bad_case_analysis JOIN probe_reports`：`probe_type = target.objectType`、`probe_object = target.objectName`、`probe_reports.object_version` 去掉 `tag:` 后等于当前版本，且 `conclusion ∈ {attributed, non_target}`。同一 case/版本可能有多条历史结论（例如 legacy 键与 V2 revision 键），按 `updated_at DESC, probe_id DESC` 取最新一条；`attributed → attributed`，`non_target → nonTarget`，没有可读行 → `unanalyzed`。因此一条 case 不会被同时算成两种状态，旧的非该对象结论也不会把新的可归因结论挤成重复行。`category` 只在 attributed 时透出，固定集合 `model|prompt|error`。
- 目标趋势的桶按状态取时间：`attributed`/`nonTarget` 用归因 `created_at`（结论产生时间），`unanalyzed` 用 `bad_cases.created_at`（上报时间）；`meta.bucketPolicy` 原样返回这条规则。窗口按 case 上报时间筛选，因此若一条归因的创建时间落在请求窗口之外，它不会出现在趋势桶里——这是分开落桶的必然结果，已在 `bucketPolicy` 声明，不把归因时间强行夹到窗口边界。
- 目标列表 `sessions` 是该对象在各版本关联 Session 的并集；summary 的 `sessions` 是各对象数值之和，所以一个 Session 同时包含多个对象时会被每个对象各算一次。summary 的 `potential`/三态同样是对象行之和，不跨对象去重；这与每个对象独立分析、独立列表的语义一致。
- 潜在 case 列表按 `createdAt DESC, badCaseId ASC, objectName, version, targetId` 稳定排序，`pageSize` 默认 8；目标列表 `pageSize` 默认 5，只影响 items，不影响 summary/total。`objects[]` 过滤的是 bad case 上报来源 `bad_cases.object_name`，`targets[]` 过滤对象 id，`states[]` 只接受三态封闭词表，空选择表示全部；`targets[]` 去重后最多 50 个，`versions[]` 最多 50 个，超限或未知状态返回 `422 VALIDATION_INVALID`。
- detail 的版本范围：显式 `versions[]` 按请求顺序取交集（未知版本忽略）；否则 `versionLimit` 取自然降序的前 N 个，`0` 表示全部，只接受 `0|5|10|20`。`stats.versions` 是本次选中版本数，`stats.sessions` 是选中版本关联 Session 的并集（包含没有潜在 case 的关联 Session），`stats.potential` 是行数，`stats.distinctCases` 是 case 去重数；`byVersion` 每个选中版本一行并零填充，`bySource` 按上报来源汇总 total 与 distinctCases，按 total 降序、来源名兜底。
- knowledge 走与 skill/agent 相同的坐标：`kind=knowledge` 的事件通常只有 `object_revision=digest:...`，版本发现保留 `digest:...`，matcher 按 revision 命中；`probe_type=knowledge` 的归因同样进入三态。没有为 knowledge 另写判定分支。
- 读边界拆成两层：`db/crud/overview_targets.py` 只做批量事实查询（窗口 case + title、对象版本事件、case 的归因链接），`service/overview/targets.py` 负责版本合并、调用 matcher、三态投影、分桶与分页。`main.py` 只新增 composition root 装配与 `app.state.target_overview`，不新增迁移、错误码或前端。
- 该 issue 不新增 UI：设计 08 §6.1 的 `TargetsOverview.vue`、TargetSideList、TargetDetailCard 与原型对齐属于 m11-04。m11-03 只交付 API 与契约，后续前端直接消费本契约。

## Alternatives considered

- **只按 `defaultRef` 分析一个版本**：实现最简单，但对象历史版本在窗口内的潜在 case 会整体消失，detail 的 `versions[]`/`byVersion` 就没有数据来源；拒绝。按事件里实际出现的版本逐版调用 matcher，才能让对象视角回看旧 revision。
- **把版本发现改成读远端 git tags**：总览会依赖网络与每个对象的仓库可用性，一次页面加载可能被 422/超时拖垮；事件里已经记录了实际出现的版本，读它更贴近「这个空间真的看到了什么」；拒绝远端查询作为首版数据源。
- **用 SQL 重写潜在匹配**：会与向导/run 出现第二套判定；issue 明确要求潜在数同源。改为每版本调用同一 `PotentialMatcher`，代价是查询次数随对象×版本增长。
- **对象级 potential 按 case 去重**：`attributed + nonTarget + unanalyzed = potential` 要求每行恰好一个状态；跨版本去重会让「v1 已归因、v2 未分析」这类真实差异消失，也让版本趋势与列表数字对不上。保留行级计数，另给 `distinctCases`。
- **同一 case/版本把所有归因行相加**：会把旧结论与新结论算成两种状态；按 newest-first 取一条，保证每行只落一态。
- **趋势把归因时间夹到窗口边界**：能让 trend 总和等于 potential，但会谎报归因发生在边界日；拒绝，保留真实时间并把「窗口外的归因不进桶」写进 `bucketPolicy`。
- **趋势用 `updated_at` 当归因时间**：缓存复用会刷新 `updated_at`，趋势会随复用次数漂移；结论产生时间用 `created_at`，`updated_at` 只用于「同一 case/版本取最新一条」的排序。
- **summary 按 Session 全集去重**：一个 Session 包含两个对象时，对象列表里的 `sessions` 会与 summary 对不上；summary 采用对象行之和，保持「每个对象独立分析」的可解释性。
- **目标列表同时套用 targets/states 过滤**：目标列表端点没有这些参数，summary 是空间级；让过滤只作用于 trend/cases/detail，避免列表页顶部数字随侧栏多选跳动。
- **detail 复用目标列表的版本范围**：单对象卡需要独立的版本与时间筛选；显式 `versions[]` 与 `versionLimit` 分开解析，时间窗也独立传入。

## Consequences

- 首屏目标总览的查询量随「启用对象数 × 窗口内出现版本数」线性增长：每个版本一次 matcher（窗口 case、Session 元数据、对象事件、agents、锚点事件、缓存键等批量查询），再加每个对象一次版本查询和一次归因查询。当前空间对象数量是人工配置的小集合，版本通常个位数；若未来单空间出现几十个对象、每对象几十个版本，需要把 matcher 的窗口/元数据装载提升为跨版本复用，或把目标分析改成异步快照。
- 目标列表、趋势、case 列表、detail 是四次独立读，不共享快照：同一屏内可能出现毫秒级不一致（刚上报/刚归因时），与既有总览四端点取舍一致。
- 趋势窗口按 case 上报时间，但 analyzed 行按归因创建时间落桶；归因发生在窗口外的行不会出现在趋势里，前端不能假设趋势总和恒等于 summary.potential。`meta.bucketPolicy` 是这条差异的唯一机器可读声明。
- 同一 case 在不同对象/版本下重复计数是有意行为；只有 detail 的 `distinctCases` 是 case 去重数，页面不能把 `potential` 与 `distinctCases` 互相替代。
- knowledge 版本以 `digest:...` 原样展示，不会转成人类可读的短 tag；UI 需要按 revision 文本展示，不能假设语义化版本。
- 本 issue 不新增错误码：目标不存在复用 `TARGET_NOT_FOUND`，过滤/版本上限复用 `VALIDATION_INVALID`；窗口与粒度错误仍走 `WINDOW_INVALID`/`GRAIN_INVALID`。
- 没有新增迁移；归因三态完全由既有 `bad_case_analysis`/`probe_reports` 推导，历史数据与 V1 legacy probe 行只要对象/版本匹配就能显示。
- 本 issue 不含前端实现与截图；m11-04 负责目标视角组件、双 Tab、单对象卡交互和视觉 E2E。
