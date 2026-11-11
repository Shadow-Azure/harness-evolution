# 17 · V2 归因进入自进化与错误详情多归因

> 本文回答：归因如何从「外部 probe 只读」改为「自进化 run 内按对象·版本生成」、潜在 bad case 的匹配策略与触发点坐标怎么定、归因缓存怎么复用、错误详情如何承载一个 bad case × 多条归因、旧 probe 链路怎么退役。
> 前置：[15 工作空间](15-v2-workspaces.md) · [16 总览](16-v2-overview.md) · [05 接口设计](05-api-design.md) · [06 数据库设计](06-database-design.md) · [07 §5 自进化](07-backend-implementation.md)。
> 验收基准：[V2 原型](../ui-prototype-v2/harness-evolution.html)（向导四步 `evRenderWizard`、运行七步 `EV_STEPS`、错误详情 `ErrorApp`/`AttributionReport`）。

## 1. 背景与目标（目标态第 6/7 点）

V1 的归因链路：外部系统写 `bad_case_analysis`（1:1）+ `probe_reports`，本服务只读；自进化的输入与聚类对象都是 probe（`probe_object@object_version`）；错误详情页一个 bad case 只有一条内嵌归因结论。

V2 把归因搬进自进化流程：

1. **启动条件不变**：选择配置好的【进化对象 + 版本 + bad case 所在时间段】（模型多选从向导 UI 移除，API 字段保留可选）。
2. **先关联 Session**：找出时间段内该工作空间上报过 bad case 的 Session，再判断该对象版本在哪些 Session 中**出现过**（出现才关联；未出现计入「跳过」统计）。
3. **再筛潜在 bad case**：对关联 Session 内的全部 bad case，按默认/自定义策略筛选。默认策略 =【对象自身上报的 self 类型】∪【触发点在对象触发点之后的 bad case】。
4. **然后归因**：对每个潜在 bad case 分析「能否归因到当前对象版本」；不能则标记**非该对象问题**（`non_target`）——它不是「未分析」，也不否定该 bad case，同一 bad case 仍可归属其它对象。
5. **归因后聚类**：按归因分类聚类、严重度降序，进入既有的 patch → push → 评测 → 接纳迭代与终评（迭代/评测/git 链路不动）。
6. **缓存可选**：启动时可选「复用缓存归因」——某对象版本已对某潜在 bad case 做过归因时，直接复用最近一次成功结果。
7. **错误详情改版**：左栏改为可折叠 bad case 组，组内按「进化对象 · 版本」列出该 bad case 的归因子项（分页）；一个 bad case 多条归因互不覆盖。

`probe_reports` / `bad_case_analysis` / `probe_cluster_probes` 三张表与 `/api/probes/*`、`/api/bad-cases/{id}/analysis` 端点进入**冻结只读**状态：历史 run 详情仍可渲染，新 run 不再读写（§11）。

## 2. 流程重排：六步 → 七步

### 2.1 步骤与状态机

| unit | step key | 标题 | done when |
|---|---|---|---|
| 0 | `range` | 选择范围 | unit ≥ 1 |
| 1 | `sessions` | Session 关联 | unit ≥ 2 |
| 2 | `potential` | 潜在 bad case | unit ≥ 3 |
| 3 | `attribution` | 对象归因 | unit ≥ 4 |
| 4 | `clusters` | 聚类与严重度 | unit ≥ 5 |
| 5 | `iteration` | 迭代优化 | unit ≥ 5 + M（M=簇数） |
| 6 | `final` | 测试集终评 | unit ≥ 5 + M + 1 |

- V1 的「聚类」「归因置信度」「严重程度排序」三步被重排为「对象归因」在前、「聚类与严重度」合并在后：归因是聚类的前置输入（按 `category` 分组），severity/rank 仍在聚类步写入。
- `progress.unit/total` 公式从 `4+M+1` 改为 `5+M+1`（原型 `evTotal = 5 + clusters + 1`）；`stageLabel` 文案同步。
- `cluster_only` 模式同样执行 0–4（聚类依赖归因），只是不建 rounds、不迭代、不终评——与 V1「cluster_only 只跑 prepare」一致，因为 prepare 现在包含归因。

### 2.2 prepare 管线（重写 `service/evolution/prepare.py`）

```text
evolution_prepare
  ① 校验 target（空间内配置且 enabled）与 policy
  ② Session 关联：空间内时间窗有 bad case 的 root sessions（投影口径 [16 §2]）
       → 对每个 session 查对象触发点（agent_events，§3）
       → 有触发点 = 关联；无 = 跳过（统计 skipped，不入表）
       → 关联结果写 run.stats 与 steps/sessions payload（不建独立关联表，见 §6 决策 A6）
  ③ 潜在筛选：对关联 session 的全部 bad case 逐条取触发点 → 按 policy 判定
       → candidates 落行（含双触发点、included、included_reason）
  ④ 归因：对 included 的候选逐条执行（§5）——缓存命中复用、未命中计算 upsert
       → conclusion=non_target 的候选保留在 candidates（可解释），不进簇
  ⑤ 聚类与排序：simple_cluster 输入换成 attributed 候选（按 category 分组）
       → probe_clusters + evolution_cluster_cases；confidence/impact/severity/rank 落库
  ⑥ build_rounds（full 模式）→ run(running) → kickoff 第一个 round
```

每步推进写 `evolution_run_events`（§10），崩溃后按 unit 游标恢复（durable 语义不变）。

## 3. 触发点坐标（trigger point）

潜在策略的「之后」比较需要 Session 内可比的坐标。归一化层补两个预计算列：

| 新列 | 表 | 写入时机 | 说明 |
|---|---|---|---|
| `triggered_at` | `agent_events`（NULL） | 归一化 | 触发事件所在 assistant message 的时间戳（从 JSONL 解析期带出） |
| `tree_index` | `agents`（NOT NULL） | 归一化 | Session 内按（父触发顺序, sort_key）DFS 赋全局递增整数，表达 spawn 先后 |

定义：

- **对象触发点**：Session 的 `agent_events` 中 `kind ∈ {skill, agent}` 且 `name == 对象名` 的事件集合（`object_type=skill → kind=skill`；`agent → kind=agent`）。**对象进入点** = 集合中坐标最小者。
- **bad case 触发点**：现有锚定算法（[06 §7.4](06-database-design.md)）算出的 `anchor` 事件；`self+agent` 且 `eventIndex=-1` 时退化为「上报 agent 的出生点」——子 agent 取父节点中 `tool_use_id` 匹配的 `agent` 事件，主 agent 取 `started_at`。
- **比较规则**（bad case 是否在对象之后）：
  1. 双方 `triggered_at` 均非空：按时间比较（精确）。
  2. 否则按 `(host_agent.tree_index, event_index)` 字典序比较（spawn 先后近似）。
  3. 双缺失 → `order_state=unknown`，该 bad case 不满足「之后」规则（只可能经 self 规则命中），候选行记 `included_reason=order_unknown`。

- 版本口径：触发事件不携带版本，「对象在该 Session 出现」按**对象名**判定；`target_version` 参与的是归因身份与缓存键（§5）。此近似写入已确认决策（§15 A4），未来 agent_events 记录版本信息后再收紧。
- 存量数据：`triggered_at`/`tree_index` 为空的行按规则 2/3 回退，不强制重放；需要时用 `pnpm data:replay:sessions` 按新 parser_version 重放补齐。

## 4. 潜在 bad case 策略（policy）

```json
{ "preset": "default" }
{ "preset": "custom", "includeSelfReport": true, "includeAfterObject": false, "sameObjectOnly": true }
```

- **默认策略** = `includeSelfReport` ∪ `includeAfterObject`：
  - `includeSelfReport`：`bad_cases.object_name == target.name AND bad_case_type == 'self'`（对象自身上报）；
  - `includeAfterObject`：同一关联 Session 内，bad case 触发点坐标 > 对象进入点。
- **自定义策略**：三开关勾选规则的并集；`sameObjectOnly` 为过滤项（只保留 `object_name == target.name` 的 bad case）；至少启用一条规则，否则 `422 POLICY_INVALID`。
- `included_reason` 封闭集合：`self_report | after_object | both | policy_excluded | order_unknown`（`both` = 两条规则同时命中）。
- policy JSON 全量快照进 `evolution_runs.potential_policy`；`policy_version` 常量随规则语义变化递增（当前 `v1`），参与缓存键。
- 匹配器实现为 `service/evolution/potential.py::PotentialMatcher`，被向导预览、run prepare、总览（[16 O2](16-v2-overview.md)）三处共用。

## 5. 归因生成与缓存

### 5.1 `bad_case_attributions`（每键一行，最新真相）

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `VARCHAR(36)` | PK | `AT-…`（ULID） |
| `workspace_id` | `VARCHAR(36)` | NOT NULL FK | — |
| `bad_case_id` | `VARCHAR(64)` | NOT NULL FK → `bad_cases` | — |
| `object_type` | `VARCHAR(16)` | NOT NULL | 归因对象身份 |
| `object_name` | `VARCHAR(128)` | NOT NULL | — |
| `object_version` | `VARCHAR(64)` | NOT NULL | 归因只作用于「对象 · 版本」 |
| `conclusion` | `VARCHAR(16)` | NOT NULL | `attributed` / `non_target` |
| `category` | `VARCHAR(16)` | NULL | `model/prompt/error`；`non_target` 时 NULL |
| `confidence` | `DOUBLE` | NOT NULL | 0–1 |
| `reason` | `TEXT` | NOT NULL | 结论说明 |
| `reasoning` | `JSON` | NOT NULL | 有序推导步骤数组 |
| `policy_version` | `VARCHAR(16)` | NOT NULL | 参与缓存键 |
| `attribution_engine` | `VARCHAR(64)` | NOT NULL | 归因引擎/模型标识（参与缓存键） |
| `created_run_id` | `VARCHAR(36)` | NULL FK → `evolution_runs` | 首次生成该结论的 run |
| `last_reused_run_id` | `VARCHAR(36)` | NULL FK | 最近一次复用的 run |
| `reused_count` | `INTEGER` | NOT NULL DEFAULT 0 | 复用次数 |
| `created_at` / `updated_at` | `DATETIME` | NOT NULL | — |

约束：`UNIQUE(workspace_id, bad_case_id, object_type, object_name, object_version, policy_version, attribution_engine)`；索引 `INDEX(bad_case_id)`、`INDEX(workspace_id, object_name, object_version)`（总览聚合）。

**缓存键**即唯一约束七元组（对应原型键：workspace + bad case + 对象身份 + 版本 + 策略版本 + 归因模型）：

- `cache_enabled=true`：键存在 → 直接复用（candidates 行 `is_cached=true`、attribution 行 `reused_count+1`、`last_reused_run_id` 更新）；不存在 → 计算后 **upsert**。
- `cache_enabled=false`：跳过缓存读，强制重算并覆盖同键行（`created_run_id` 更新为本次 run）。
- 归因结论**只作用于该对象·版本**：不修改 bad case 本身，不影响它与其它对象的潜在关系（原型「结论边界」文案）。

### 5.2 V2 占位归因引擎（可替换钩子）

`service/evolution/attribution.py::AttributionEngine`，默认实现 `RuleBasedEngine`（`attribution_engine="rule-v1"`），规则表：

| 条件 | conclusion | category | confidence |
|---|---|---|---|
| `included_reason ∈ {self_report, both}`（对象自身上报） | `attributed` | 按 `meta_data` 错误特征判定：含 error/exception → `error`；否则 `prompt` | 0.8 |
| `after_object` 且 bad case 为 `discovery` | `attributed` | `error`（占位） | 0.6 |
| `after_object` 但 `order_state=unknown`，或证据不足（`meta_data` 为空且描述无错误特征） | `non_target` | NULL | 0.7 |

- `reason`/`reasoning` 生成占位文案（含触发点对照、策略、证据引用），格式与原型一致；后续接 LLM 时只换 Engine 子类 + 注册新 `attribution_engine` 标识（与 `EvolutionEngine` 工厂同一模式，[07 §5.4](07-backend-implementation.md)），表与 API 不变。
- 引擎标识进缓存键：换引擎不污染旧结论。

## 6. 运行候选与聚类关联

### 6.1 `evolution_run_candidates`（一次 run 的可解释快照）

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `VARCHAR(36)` | PK | — |
| `run_id` | `VARCHAR(36)` | NOT NULL FK → `evolution_runs` ON DELETE CASCADE | — |
| `workspace_id` | `VARCHAR(36)` | NOT NULL | 冗余，便于空间审计 |
| `session_id` | `VARCHAR(36)` | NOT NULL | 关联 Session |
| `bad_case_id` | `VARCHAR(64)` | NOT NULL FK → `bad_cases` | — |
| `object_trigger_agent_id` / `object_trigger_event_index` / `object_trigger_at` | `VARCHAR(64)` / `INTEGER` / `DATETIME` | NULL | 对象触发点（进入点） |
| `case_trigger_agent_id` / `case_trigger_event_index` / `case_trigger_at` | 同上 | NULL | bad case 触发点 |
| `order_state` | `VARCHAR(16)` | NOT NULL | `comparable` / `unknown` |
| `included` | `BOOLEAN` | NOT NULL | 是否命中策略 |
| `included_reason` | `VARCHAR(16)` | NOT NULL | §4 封闭集合 |
| `attribution_id` | `VARCHAR(36)` | NULL FK → `bad_case_attributions` | 本次 run 关联的归因行 |
| `is_cached` | `BOOLEAN` | NOT NULL DEFAULT false | 本次是否走缓存 |
| `cluster_id` | `VARCHAR(64)` | NULL FK → `probe_clusters` | attributed 且入簇后回填 |
| `created_at` | `DATETIME` | NOT NULL | — |

约束：`UNIQUE(run_id, bad_case_id)`（一个 run 内一条 bad case 一行）；索引 `INDEX(run_id, included)`、`INDEX(bad_case_id)`、`INDEX(attribution_id)`。

- **Session 关联结果不单独建表**：关联 Session 集合可由 candidates `DISTINCT session_id` 推导（跳过的 Session 只进 `run.stats` 与 steps payload——它没有 bad case 候选行可落）。向导第 2 步分页预览直接查同一推导。
- 候选行在策略判定阶段全量落库（含 `included=false`，`included_reason=policy_excluded`）：运行详情可解释「为什么这个 bad case 没进潜在」。

### 6.2 `evolution_cluster_cases`（簇 ↔ 候选）

| 列 | 类型 | 约束 |
|---|---|---|
| `probe_cluster_id` | `VARCHAR(64)` | PK 组成, FK → `probe_clusters` ON DELETE CASCADE |
| `candidate_id` | `VARCHAR(36)` | PK 组成, FK → `evolution_run_candidates` ON DELETE CASCADE |

- `probe_clusters` 表沿用（`confidence/impact/severity/rank` 语义不变；`probe_cluster_type` 取值改由归因 `category` 驱动）；`probe_cluster_probes` 停止写入（历史 run 保留只读）。
- `simple_cluster` 的分组键从 `probe.attribute_type` 换成 `attribution.category`；「按类型对半拆」的占位算法逻辑保留，输入换源。

## 7. 向导四步与启动 API

向导从两步扩为四步（`pages/evolution/components/LaunchWizard.vue` 重写），预览端点全部 `POST`（条件体）+ 空间前缀：

| 步 | 端点 | 请求关键字段 | 响应 |
|---|---|---|---|
| ① 选择范围（纯前端表单） | — | 对象/版本（targets 空间内已配置启用的候选）+ 时间段 + policy + （可选从 bad case 锁定 `focusCaseId`） | — |
| ② Session 关联 | `POST /api/workspaces/{wid}/evolution/preview/sessions` | `{targetType,targetName,targetVersion,from,to,page,pageSize=4}` | `{summary:{reportedSessions,associatedSessions,skippedSessions},items:[{sessionId,title,objectTriggerAt,badCaseCount,potentialCount}],total,page,pageSize}` |
| ③ 潜在 bad case | `POST .../preview/potential` | 同上 + `policy`、`pageSize=5` | `{summary:{badCases,potential},items:[{badCaseId,objectName,badCaseType,triggerAt,sessionId,hitReason}],total,page,pageSize}` |
| ④ 归因预览与启动 | `POST .../preview/attribution` | 同上 + `cacheEnabled` | `{summary:{potential,reused,fresh,nonTargetKnown}}` |
| 启动 | `POST /api/workspaces/{wid}/evolution/runs` | `{targetType,targetName,targetVersion,from,to,models?,policy,cacheEnabled,mode:"full",engineKey?,eval?}` | `202 {runId,jobId,status:"preparing"}` |
| 仅聚类 | `POST .../cluster-previews` | 同上（`mode:"cluster_only"`） | 同上 |

- 第 ④ 步预览**不执行归因**：`reused` = 潜在集合中缓存键已命中的精确数；`fresh = potential - reused`；`nonTargetKnown` = 该对象已有 `non_target` 结论的去重 bad case 数（历史参考值）。四数语义在 UI 副标题写明。
- 同步校验沿用 V1：`TARGET_NOT_CONFIGURED`（空间内）/ `NO_POTENTIAL_MATCHED`（potential=0 时 409，向导映射为空态并禁用出口）/ `POLICY_INVALID`。
- `focusCaseId`：从错误详情「以该 bad case 启动自进化」进入时预填并锁定该 bad case 的 Session/对象线索（仅前端行为，不进 API）。
- 模型多选从向导 UI 移除；`models` 字段保留可选（缺省=全部），与 V1 run 表兼容。
- 旧 `POST /api/evolution/probes/query` **移除**（生产无存量消费者；contracts 重新生成）。

## 8. 运行详情七步 payload

`steps[]` 的 `key` 换为七步；每个 step 独立端点（`GET /runs/{rid}/steps/{key}`）与外壳结构（[05 §3.6](05-api-design.md)）不变：

| step | payload 关键字段 |
|---|---|
| `range` | `condition`（target/版本/时间窗/policy/cacheEnabled/workspace）、`stats`（reported/associated/skipped/badCases/potential） |
| `sessions` | `summary` + `rows[]`（sessionId/title/objectTriggerAt/badCaseCount/potentialCount），4 条/页 |
| `potential` | `summary` + `rows[]`（badCaseId/objectName/badCaseType/triggerAt/sessionId/**hitReason**），5 条/页 |
| `attribution` | `summary{potential,reused,fresh,nonTarget}` + `rows[]`（badCaseId/attributionId/category/description/**source: cached\|fresh**/confidence）；对象·版本在 step 标题，不在行内重复 |
| `clusters` | `clusters[]`：`{probeClusterId,title,description,category,probeCount→caseCount,confidence,severity,rank,cases[]}`；按 severity 降序，每簇可折叠，展开列出来源 bad case（ID 可深链错误详情），默认展开第一簇 |
| `iteration` | `rounds[]` 沿用 V1 结构；`probes[]` 换成 `cases[]`（badCaseId/title/objectName/badCaseType/triggerAt/createdAt） |
| `final` | 不变 |

- `RunCard` 增补：空间 badge、策略（默认/自定义）、缓存开关 chips、统计（关联 Session/潜在/可归因/复用归因/已跑轮次）。
- **历史 run（V1 六步）兼容**：`steps[]` 由后端从数据推导，V1 run 仍返回旧六步 key 与 probe 语义 payload；前端 `RunStepContent` 按 `key` 动态渲染，新旧组件并存（旧组件只读冻结，不再迭代）。`runId` 落在哪个版本由 `evolution_runs.steps_schema`（`v1`/`v2`，建行时写入）判定，前端不猜。

## 9. 错误详情多归因（目标态第 7 点）

### 9.1 API

| 端点 | 说明 |
|---|---|
| `GET /api/workspaces/{wid}/bad-cases/{badCaseId}/attributions?page=1&pageSize=2` | `{items:[{attributionId,objectType,objectName,objectVersion,conclusion,category,confidence,runId,isCached,createdAt}],total,page,pageSize}`；按 `updated_at` 倒序 |
| `GET .../attributions/{attributionId}` | 完整归因：上表字段 + `reason/reasoning/policyVersion/attributionEngine/reusedCount` + `triggerCompare{objectTriggerAt,caseTriggerAt,order}`（取该归因最近一次关联的 candidates 行） |

- 现有 `GET /sessions/{sid}/bad-cases` 的 `BadCase` 增补 `attributionCount`（该 bad case 的归因条数）与 `hasAttribution`，供左栏父行与筛选 chips 使用；`analysis` 字段保留（V1 冻结语义）但前端不再消费。

### 9.2 前端（`pages/errors/*` 改造）

- 左栏改为**可折叠 bad case 组**（`ErrorSidebar.vue` 重写）：
  - 顶部筛选 chips：全部 / 有归因 / 待归因；
  - 父行：`#no` + badCaseId（深链）+ 标题 + self/discovery badge + object_name + 归因数；
  - 展开后按「进化对象 · 版本」列出归因子项（结论、时间、缓存标记），**每页 2 条**分页；
  - 点父行 → 问题描述 Tab；点子项 → 归因分析 Tab 并定位该条。
- 归因分析 Tab（`AttributionReport.vue` 重写）固定顺序：结论横幅（可归因到本对象 / 非该对象问题）→ 分类 → 对象 · 版本 + 归因来源 run（可跳运行详情）+ 时间 + 缓存来源 → 置信度 + 策略 → 对象触发点 vs bad case 触发点对照 → 归因结论说明 → 推导过程 → 结论边界说明。
- 多条归因导航：`N / total` 与上一条/下一条切换；深链 `?case=&tab=attr&at={attributionId}`（`obj={objectName}` 兼容定位第一条匹配）。
- 无归因 bad case：显示「尚未归因」空态 + 说明文案（归因在自进化流程中生成）+「以该 bad case 启动自进化 →」（有权限时，拉起向导并预填 `focusCaseId`）。
- 执行流、问题描述 Tab、全部错误恢复行为保持 V1。

## 10. SSE 与执行事件增补

`evolution_run_events.event_type` 新增（外壳与 `run.event` 推送机制不变）：

| 事件 | 阶段 | payload 示例 |
|---|---|---|
| `sessions_linked` | prepare | `{reported, associated, skipped}` |
| `potential_computed` | prepare | `{badCases, potential, policy}` |
| `attribution_reused` | prepare | `{badCaseId, attributionId, objectName, objectVersion}` |
| `attribution_created` | prepare | `{badCaseId, attributionId, conclusion, category}` |

- `run.progress` 的 `stageLabel` 按 §2.1 文案生成；`percent` 分母改 `5+M+1`。
- topics 仍只有 `run:{rid}`；`GET /runs/{rid}/events` 同步支持新 eventType 过滤。

## 11. 兼容与迁移

| 对象 | 处置 |
|---|---|
| `bad_case_analysis` / `probe_reports` | 冻结只读：生产无写入路径（现状即外部只读），V2 起不再被自进化/错误页消费；历史 run 详情（V1 steps payload）仍读 |
| 存量 `analyzed_issue` 数据 | 一次性导入 `bad_case_attributions`：object=`probe_type/probe_object/object_version`，conclusion=`attributed`，category=`attribute_type`，confidence=0.8（占位），reason=`probe_description`，reasoning=`[probe_analysis]`，engine=`legacy-probe-import`，run_id=NULL；生产无数据，导入仅对 fixtures/开发库执行 |
| 存量 `analyzed_nonissue` | **不迁移**：「非问题」与「非该对象问题」是不同谓词（前者否定 bad case 本身）；历史 bad case 视为未归因 |
| `/api/probes/{id}`、`/api/bad-cases/{id}/analysis` | 标记 deprecated 保留一个版本（历史脚本兼容），下个大版本删除；错误页不再调用 |
| `POST /api/evolution/probes/query` | 移除（§7） |
| 旧 `?issue=` 深链 | 生产无存量，不做 probe 深链兼容；`issue` 参数解析为 badCaseId 的旧格式同样无存量，直接下线 |
| contracts | `pnpm contract:generate` 重出；steps 新 key、attribution 模型、预览端点全部进快照 |

## 12. 代码改动地图

| 层 | 文件/模块 | 改动 |
|---|---|---|
| 归一化 | `service/acquisition/agent_tree.py`、`db/crud/acquisition_replay.py`、`db/models/domain.py` | `agents.tree_index`、`agent_events.triggered_at` 两列 + 解析器带出时间戳；`parser_version` 递增触发重放 |
| 匹配器 | `service/evolution/potential.py`（新） | `PotentialMatcher`（触发点坐标 + 策略判定），预览/prepare/总览共用 |
| 归因 | `service/evolution/attribution.py`（新） | `AttributionEngine` + `RuleBasedEngine` + 缓存读写（upsert/复用计数） |
| 管线 | `service/evolution/prepare.py`、`stages.py`、`state.py` | §2.2 管线重写、七步状态机、`steps_schema` |
| 聚类 | `service/evolution/cluster.py` | 输入换 candidates/category；`evolution_cluster_cases` 写入 |
| 启动 | `service/evolution/launch.py`、`probe_query.py`（删）、`api/evolution_launch.py` | 新 body 字段、三段预览端点、`NO_POTENTIAL_MATCHED` |
| 读模型 | `service/evolution/runs.py` | 七步 payload 装配 + V1 run 旧 payload 兼容 |
| 存取 | `db/crud/candidates.py`、`attributions.py`、`cluster_cases.py`（新） | §5/§6 表 |
| 路由 | `api/problems.py` 扩展、`api/evolution_runs.py` | attributions 分页/详情端点、空间前缀 |
| 前端 | `LaunchWizard.vue`（四步）、`RunDetail.vue` + `StepRange/StepSessions/StepPotential/StepAttribution/StepClustersV2`、`ErrorSidebar.vue`/`AttributionReport.vue` | §7–§9 |
| fixtures | `fixtures/` | 空间化样例 + 触发点数据 + 3–4 条多归因 bad case（约 1/5 未归因，对齐原型分布） |

## 13. 测试与验收

- 端到端：seed → 向导四步（② 只列对象出现过的 Session、③ 命中原因列正确、④ 四数一致）→ 启动 → 七步详情（簇按 severity 降序、来源 bad case 可深链）→ 错误页左栏折叠/分页/定位。
- 缓存：同条件第二次 run，`attribution` 步 `reused == potential`、attribution 行 `reused_count` 递增；`cache_enabled=false` 强制重算覆盖。
- 策略：默认策略两支各自的命中/未命中用例；`sameObjectOnly`、`order_unknown` 回退；`POLICY_INVALID` 422。
- 触发点：`triggered_at` 精确比较、缺失回退 `(tree_index, event_index)`、双缺失 `order_unknown`。
- 非该对象：`non_target` 候选不进簇、错误页可见、同一 bad case 的其它对象归因不受影响。
- 历史 run：V1 run 详情仍按六步渲染（steps_schema=v1）。
- `pnpm test:api`（管线单测）+ `pnpm test:gates` + `pnpm contract:check` + `pnpm test:e2e -- --pattern "evolution|errors"`。

## 14. 非目标

- 真实 LLM 归因（引擎接缝已留，规则占位先行）。
- 单 bad case 手动触发归因（只能经自进化 run 产生）。
- 归因结论跨对象合并/冲突仲裁（多条结论并存，不做权威排序）。
- 向导/详情之外的政策编辑器（三开关即全部自定义面）。
- V1 六步详情页的视觉翻新（只冻结维护）。

## 15. 已确认决策

| # | 决策 | 依据 |
|---|---|---|
| A1 | 归因由本服务在 run 内生成，`bad_case_attributions` 每缓存键一行、最新真相、复用计数 | 目标态第 6 点；错误详情天然分页查询 |
| A2 | 「非该对象问题」是一等结论（`non_target`），不等于未分析、不否定 bad case | 目标态第 6 点；多对象互不覆盖 |
| A3 | 缓存键七元组：workspace + bad case + 对象身份 + 版本 + 策略版本 + 归因引擎 | 原型缓存键文案；换引擎/换策略不串缓存 |
| A4 | Session 关联按对象名（触发事件不带版本）；版本只进归因身份 | 数据现状；写入遗留项：agent_events 记录版本后收紧 |
| A5 | 触发点比较：`triggered_at` 优先，`(tree_index, event_index)` 字典序兜底，双缺失不满足「之后」 | 跨 agent 行号不可比；时间戳精确但存量缺失 |
| A6 | 候选表全量落库（含 excluded），Session 关联由候选推导不建独立表 | 可解释性优先；避免双表同步 |
| A7 | 聚类输入换 `attribution.category`，簇表沿用、成员表新起 `evolution_cluster_cases` | `probe_cluster_probes` 语义已变，另起干净的表 |
| A8 | `analyzed_nonissue` 不迁移、旧 probe 深链不做兼容 | 生产无存量；谓词不同 |
| A9 | 前端双轨渲染新旧 steps（`steps_schema` 判定） | 历史 run 不可重算 |
| A10 | 向导 UI 移除模型多选，API 字段保留 | 原型行为；减少与归因无关的筛选项 |
