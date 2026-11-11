# 16 · V2 工作空间总览与 Session 列表

> 本文回答：工作空间总览页（bad case 总览 / 进化对象总览双视角）看什么、每个数字的口径与 SQL 怎么算、聚合接口怎么切、Session 错误查看页的「最新 10 条 + 回车查询」怎么改、性能与边界怎么守。
> 前置：[15 工作空间](15-v2-workspaces.md)（空间模型与权限）· [05 接口设计](05-api-design.md) · [06 数据库设计](06-database-design.md)；配套：[17 归因](17-v2-attribution.md)（潜在 bad case 与归因口径）。
> 验收基准：[V2 原型](../ui-prototype-v2/harness-evolution.html) 总览页（`v2RenderOverview` / `v2RenderTargetsOverview` / `v2TargetDetailCard`）。

## 1. 背景与目标

V1 没有 Dashboard：登录后直接进 Session 列表，问题数据只能按会话逐个看。V2 给每个工作空间一个总览页，回答三个问题：

1. 这个空间的 bad case 总量、`self`（自身存在问题）/ `discovery`（发现前置步骤问题）构成、时间趋势如何？（目标态第 4 点前半）
2. 按不同 `bad_cases.object_name`（bad case 上报来源）分别是什么情况？——多选筛选，不选即全部。
3. 从时间、来源、类型任意组合下钻到具体 bad case，一键进入 Session 错误详情对应问题。

同时把 Session 错误查看页的默认行为从「全量拉取 + 实时过滤」改为「最新 10 个 + 回车精确查询」（目标态第 5 点）。

页面文案映射（展示层统一，字段原名不变）：`self` → 「自身存在问题」；`discovery` → 「发现前置步骤问题」；`object_name` → 「bad case 上报来源」。

### 1.1 页面结构总览

```text
/workspaces/:wid/overview
├── 一级 Tab：bad case 总览 | 进化对象总览   （URL: ?tab=cases|targets）
├── 共享上下文：时间范围 ?range=7|30|90|0&from=&to= + 粒度 ?grain=day|week|month
│
├── [tab=cases]
│   ├── statstrip（6 项）────────────────────────────── GET /overview/summary
│   ├── 趋势卡 ───────────────────────────────────────── GET /overview/trend
│   │   ├── 来源多选下拉（?objects=ws:… 逗号分隔，空=全部）
│   │   └── 堆叠柱图（self 蓝 / discovery 紫）+ 图例
│   ├── 来源分布卡 ─────────────────────────────────── GET /overview/sources
│   └── 明细矩阵（来源 × 时间桶，可折叠，前端用 trend 数据拼装，不另出接口）
│
└── [tab=targets]
    ├── statstrip（6 项）────────────────────────────── GET /overview/targets（汇总字段）
    ├── 趋势卡（对象多选 + 三态 chip）───────────────── GET /overview/targets/trend
    ├── 两块分布（关联 Session / 潜在 bad case）──────── 同上响应内 buckets[].byTarget
    ├── 右侧对象列表（5/页，可进化排序）─────────────── GET /overview/targets
    ├── 单个进化对象分析卡 ───────────────────────────── GET /overview/targets/{id}/detail
    └── 潜在 bad case 列表（8/页，组合筛选）──────────── GET /overview/targets/cases
```

- 下钻深链：`/workspaces/:wid/sessions/:sid/errors?case={badCaseId}&tab=desc`（行内 ID 链接、新窗口打开；整行不可点击，沿 [原型第十七轮决策](../../.agents/notes/implemented/bug-fix/2026-11-11-ui-prototype-v2-ui-polish.md)）。
- 页面级 URL 状态：`tab`、`range`、`from`/`to`、`grain`、`objects`（多选来源）、`badCaseType`、`page`、`targets`（对象多选）、`states`（三态）、`targetPage`。刷新可恢复；切换空间清空除 `tab` 之外的参数。

### 1.2 与 V1 的边界

- 本文只定义读模型与聚合接口；写入（上报、额度）在 [15 §4.4](15-v2-workspaces.md)，归因与潜在匹配在 [17 §4–§5](17-v2-attribution.md)。
- V1 的 Session 详情三接口（`GET /sessions/{sid}`、`/tree`、`/bad-cases`）结构不变，只加空间前缀与校验（§5.1）；V1 的列表页 `GET /api/sessions` 端点冻结（[15 §7](15-v2-workspaces.md)）。

## 2. 口径定义（总览所有数字的唯一出处）

### 2.1 基础集合与计数

设 `C(wid, from, to) = { bad_case | workspace_id = wid AND created_at ∈ [from, to] }`：

| 指标 | 公式 | SQL 要点 |
|---|---|---|
| bad case 总数 | `\|C\|` | `COUNT(*)`，走 `INDEX(workspace_id, created_at)` |
| 自身存在问题 | `\|{ c ∈ C : c.bad_case_type = 'self' }\|` | `GROUP BY bad_case_type` |
| 发现前置步骤问题 | `\|{ c ∈ C : c.bad_case_type = 'discovery' }\|` | 同上，一次查询取两值 |
| 关联 Session | `\|{ c.bad_case_session_id : c ∈ C }\|` | `COUNT(DISTINCT bad_case_session_id)` |
| 上报来源数 | `\|{ c.object_name : c ∈ C }\|` | `COUNT(DISTINCT object_name)` |
| 额度使用 | `used = COUNT(bad_cases WHERE workspace_id=wid)`（**不带时间窗**） | 与 [15 §3.2](15-v2-workspaces.md) 同一口径；总览里显示 `used/quota` 进度条 |
| 待轨迹同步 Session | `\|{ s ∈ 关联 Session : s ∉ session_families }\|` | `LEFT JOIN session_families … WHERE id IS NULL`，前端在统计卡角标提示 |

**空间 Session 集合** = 上述 `DISTINCT bad_case_session_id` 的合法取值再 `JOIN session_families`（已归一化的部分）。未归一化的 Session 不进列表，只计入「待轨迹同步」。

### 2.2 时间与分桶

- 时间语义：按 `bad_cases.created_at`（**上报时间**，不是 Session 启动时间）。理由：总览回答「问题什么时候被上报/被发现」，与 Session 的生命周期解耦；会话列表才按 `started_at`。
- 时区：所有边界按 Asia/Shanghai 计算（`[from 00:00:00, to+1 00:00:00)` 左闭右开），存储层是同一时区的 `DATETIME`，无 UTC 换算。
- 粒度：`day`（`YYYY-MM-DD`）、`week`（ISO 周，周一起，标签 `2026-W45`）、`month`（`YYYY-MM`）。
- 空桶补零：服务端按时间窗生成完整桶序列，缺数据填 0（前端不插值，也不画断点）。
- 时间窗上限：`to - from ≤ 366 天`，超出 `422 VALIDATION_INVALID`；`range=7|30|90` 时 `from/to` 由服务端推导，`range=0` 表示自定义且必须同时给 `from`/`to`。

### 2.3 潜在 bad case（对象视角）

| 指标 | 公式 |
|---|---|
| 关联 Session（对象） | 空间 Session 集合中**出现过该对象触发点**的 Session 数（触发点定义见 [17 §3](17-v2-attribution.md)；按对象名聚合时不区分版本） |
| 关联 bad case（对象） | 这些关联 Session 内的 bad case 总数（不按策略过滤，用于解释「潜在」与「全部」的差额） |
| 潜在 bad case | 上述集合按**默认潜在策略**命中数（[17 §4](17-v2-attribution.md) 的 `PotentialMatcher`，与向导/run 同一实现） |
| 是该对象 / 非该对象 / 未分析 | 潜在集合中已有 `bad_case_attributions`（对象·版本）记录：`conclusion=attributed` / `non_target` / 无记录（[17 §5](17-v2-attribution.md)） |
| 可进化量 | `是该对象 + 未分析`（右侧对象列表的排序键） |

**为什么总览不另造近似口径**：用户会在同一屏对比「总览潜在数」与「向导第 3 步潜在数」，任何近似都会立刻表现为数字不一致。因此三处共用一个实现，只是调用形态不同：

```text
向导预览：单个对象 + 时间窗 → PotentialMatcher.match(object, window)     （同步、分页）
run prepare：同一调用，结果落 evolution_run_candidates（[17 §6](17-v2-attribution.md)）
总览：N 个对象（或全部对象）→ 逐对象调用 + 60s 缓存；批量场景见 §7.3
```

### 2.4 边界情况矩阵

| 情况 | 表现 | 处理 |
|---|---|---|
| Session 轨迹未归一化 | 关联 Session 无法验证对象是否出现 | 计入「待轨迹同步」；不参与潜在计算；补齐后下一轮刷新自动进入 |
| 同一 `badCaseId` 重复上报 | 只有一行（upsert） | 计数天然去重；列表按 `updated_at` 排序时后写覆盖 |
| 同一 Session 被多个空间上报 | 两个空间各看到自己那份 | 空间投影口径的必然结果；不合并 |
| 跨月/跨年时间窗 | 桶标签跨年 | 周用 ISO 周（含年份），月用 `YYYY-MM` |
| 上报时间缺失 | `createdAt` 必填时不允许；缺省用服务端时间 | 无「无桶」数据 |
| 时间窗内零数据 | 图表空态 + 列表空态 | 服务端仍返回完整桶序列（全 0），前端显示空态文案而非空白图 |
| 对象已被删除（targets 移除） | 历史归因仍在 | 总览按 `object_name` 聚合（来自 bad_cases / attributions），不读 targets 表决定历史；对象列表只列**当前启用**的对象 |
| 额度为 0 的空间 | 统计条显示 0/0 | 上报立即 409；总览正常显示历史数据（若有） |

## 3. bad case 总览

### 3.1 指标条（statstrip，6 项）

bad case 总数 · 自身存在问题 · 发现前置步骤问题 · 关联 Session · bad case 上报来源数 · 额度使用（`used / quota`）。全部来自 `GET .../overview/summary` 一次返回（静态元数据聚合，符合 [05 §1.1](05-api-design.md)）。

交互：点击「自身存在问题」「发现前置步骤问题」→ 把 `badCaseType` 写入列表筛选并滚动到列表；点击「上报来源数」→ 聚焦来源多选。指标条本身不随 `objects` 多选变化（它是空间全景），只有列表与来源分布随筛选变化——与原型一致。

### 3.2 趋势卡

- 时间选择：近 7 / 30 / 90 天或自定义区间；粒度日 / 周 / 月。
- 「bad case 上报来源」多选下拉：不选 = 全部；多选 = 并集；选中项以 chip 展示、可逐项移除；下拉内提供搜索与「全选当前页」。
- 主图：按时间桶堆叠 self（蓝）/ discovery（紫）柱状图。
  - Y 轴：`max = max(bucketTotal)`；刻度取 1/2/5×10ⁿ 的整刻度（4 段），刻度值向上取整。
  - 柱高：`h = value / max * plotHeight`；`value=0` 不画柱。
  - 柱宽：`min(28px, plotWidth / bucketCount * 0.6)`；桶数 > 60 时改为「按周聚合」提示（避免不可读）。
  - 悬浮：tooltip 显示桶标签、self/discovery 数值与占比；点击桶 → 列表按该桶时间过滤。
- 来源分布：按 `object_name` 汇总总量与 self/discovery 占比（原型 top6 条形 + 「其余 N 个来源」折叠）。点击条形 = 切换该来源的选中态（与下拉联动）。
- 明细矩阵：来源 × 时间桶的展开表格（行 = 来源，列 = 桶，单元格 = 该来源该桶的 self+discovery 合计），前端用 trend 的 `buckets[].byObject` 拼装，不额外请求。

#### 3.2.1 图表坐标与刻度算法（前端纯函数，可单测）

```ts
// 刻度：1/2/5 × 10^n 的 4 段「漂亮刻度」，向上取整
export function niceTicks(max: number, segments = 4): number[] {
  if (max <= 0) return [0, 1, 2, 3, 4]
  const rawStep = max / segments
  const mag = 10 ** Math.floor(Math.log10(rawStep))
  const norm = rawStep / mag
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag
  const top = Math.ceil(max / step) * step
  return Array.from({ length: segments + 1 }, (_, i) => i * step).filter((v) => v <= top)
}

// 柱布局：宽度自适应，超过 60 桶时提示降级（服务端也会强制降级，见 §6.3）
export function barLayout(count: number, plotWidth: number) {
  const slot = plotWidth / Math.max(count, 1)
  const barWidth = Math.min(28, Math.max(2, slot * 0.6))
  return { slot, barWidth, degraded: count > 60 }
}

// 堆叠：self 在下、discovery 在上；0 值不画
export function stackY(self: number, discovery: number, top: number, plotHeight: number) {
  const scale = (v: number) => (v / top) * plotHeight
  const ySelf = plotHeight - scale(self)
  const yDiscovery = ySelf - scale(discovery)
  return { ySelf, hSelf: scale(self), yDiscovery, hDiscovery: scale(discovery) }
}
```

- 刻度函数与柱布局是纯函数，放 `pages/overview/chartGeometry.ts` 并配单测（空数据、极大值、单桶、60+ 桶边界）。
- `niceTicks` 的 `top` 与 §3.2 的 `max` 不同：`max` 是数据最大值，`top` 是刻度上界（≥ max），柱高按 `top` 归一，保证最高柱不贴顶。


### 3.3 列表与分页

- 筛选：时间段、上报来源（多选）、类型（self/discovery/空=全部）。三者独立于图表筛选（原型行为）：图表用 `objects`，列表用 `objects + badCaseType + from/to`。
- 分页：8 条/页；`total` 由服务端给；页码超界时返回最后一页（不报错）。
- 列：bad case ID（深链）/ Session 标题（点击进入该 Session 概览）/ 来源 `object_name` / 类型 badge / 标题 / 上报时间 / 归因数（`attributionCount`）。
- 排序：固定 `created_at DESC`（V2 不提供排序切换）。
- 空态：「当前筛选下没有 bad case」+ 「清除筛选」按钮。

## 4. 进化对象总览（二级 Tab）

与 bad case 总览共享空间与时间上下文（切换 Tab 不重置时间窗），布局对齐原型：

- 指标条 6 项：对象数、关联 Session、潜在 bad case、是该对象、非该对象、未分析。其中「对象数」= 当前空间启用的 targets 数；其余按全部启用对象的并集统计（去重：同一 Session 可被多个对象关联，按对象视角分别是不同计数，指标条给「去重后」总数并标注）。
- 趋势图：多选进化对象 + 「查看信息」三态 chip（是该对象 / 非该对象 / 未分析）控制堆叠信息；每个桶按三态堆叠，`unanalyzed` 用灰色。
- 分布块：「不同进化对象的关联 Session」（潜在 / 仅关联两段）与「不同进化对象的潜在 bad case」，柱长按最大值归一。
- 右侧对象列表：5 条/页，按「可进化潜在 bad case 数量（是该对象 + 未分析）」降序、并列按潜在总数、再按对象名；每项显示对象/版本（`defaultRef`）、关联 Session、潜在数、可进化数；空间管理员可直接新增/编辑/移除（复用 targets CRUD，[15 §3.5](15-v2-workspaces.md)）。
- 底部潜在 bad case 列表：8 条/页；筛选 = 进化对象（多选）+ 上报来源 + 状态（是/非/未）+ 时间段；列：bad case ID（深链）/ 进化对象·版本 / 上报来源 / 状态 badge / 上报时间 / Session / 归因报告 ID（有则链接到归因分析 Tab）/ 问题现象（描述，超长省略 + title）。
- 单个进化对象分析卡：对象下拉必选（默认第一个启用对象，无对象时置空并给「去配置进化对象」入口）+ 版本多选（默认最近 5，可选 5/10/20/全部）+ 独立时间段（不跟随总览）；统计：关联 Session、潜在 bad case、去重后、覆盖版本；两块分布：按版本的潜在 bad case 三态堆叠、按来源的去重数量。

版本口径（分析卡）：`object_version` 取**归因行的版本**（`bad_case_attributions.object_version`，[17 §5](17-v2-attribution.md)）与 `bad_cases.object_version`（上报者版本）的并集；同一 bad case 在不同版本下可能重复出现在多个版本分组（原型注释：这不是缓存或重复上报，而是口径本身如此）。「去重后」= `COUNT(DISTINCT bad_case_id)`。

## 5. Session 列表改造（目标态第 5 点）

### 5.1 口径与接口

- 列表 = **当前空间**的 Session 集合（§2.1 投影），按 `started_at` 倒序取前 10；标题显示「最新 10 / 总数 N」。
- `GET /api/workspaces/{wid}/sessions?q=&status=&sort=&limit=10`：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `q` | string | `""` | 标题/仓库/根会话 ID 的模糊匹配（`search_text LIKE` + `id LIKE`，大小写不敏感）；语义保持 [13 §4](13-root-session-id.md) |
| `status` | `all\|ok\|partial\|fail\|problem` | `all` | 与 V1 相同 |
| `sort` | `latest\|userTurns\|messages\|agents` | `latest` | 与 V1 相同 |
| `limit` | int | **10**（V2 默认；上限 500） | V1 默认 100 |

- 响应新增 `total`：`SessionListResponse { items, total, pendingSessions }`，`pendingSessions` = 空间内 bad case 涉及但未归一化的 Session 数（前端在标题旁提示「N 个待同步」）。
- 会话概览/执行流/问题列表三接口结构不变（只加空间前缀）：`GET /workspaces/{wid}/sessions/{sid}`、`/tree`、`/bad-cases`。

### 5.2 搜索交互状态机

```text
[idle] 输入框为空，列表 = 最新 10
  │ 用户输入并回车（Enter / 搜索按钮）
  ├─ q 为空 → 清空筛选，回到 [latest]
  └─ q 非空 → GET sessions{q, limit:10}
        ├─ total > 0 → [search] 左侧替换为结果（默认选中第一条），URL 写 ?q=
        └─ total = 0 → [empty] 左栏空态「未找到匹配 'xxx' 的 Session」，右栏空态
                      不保留旧选中（避免看错对象）
[search] 清空输入再回车 → 回到 [latest]
```

- 移除 V1 的 300ms 防抖实时查询：逐键触发会对 `search_text` 全表 LIKE，数据量上去后不可控；回车触发是显式动作，语义也更清楚。
- 输入框让位给「ID 优先」提示：placeholder 为「输入 Session ID 或标题关键词，回车查询」。
- `q` 与 `status`/`sort` 可组合；组合后仍按 `limit=10`。

### 5.3 未命中与权限

- 未命中：左右两栏各自空态（左「未找到匹配的 Session」+ 「恢复最新 10」按钮；右「选择左侧 Session 查看详情」）。
- Session 不属于当前空间：`GET /workspaces/{wid}/sessions/{sid}` → `404 SESSION_NOT_FOUND`（与不存在同码，防跨空间探测）；前端跳回列表并 toast。
- 空间无任何 bad case：列表空态「该工作空间还没有上报 bad case」+ 上报接入链接（空间管理员可见）。

## 6. API 契约

全部挂 `require_workspace_role(wid, "viewer")`（[15 §2.5](15-v2-workspaces.md)），响应 camelCase，错误信封统一。

### 6.1 通用参数对象

```json
{ "from": "2026-10-01", "to": "2026-11-11", "grain": "day",
  "objects": ["deep-research", "code-review"], "badCaseType": null,
  "page": 1, "pageSize": 8 }
```

- `objects`：来源名（`object_name`）数组，空数组 = 全部；去重、trim、每项 ≤128、最多 50 项（超出 422）。
- `badCaseType`：`self|discovery|null`；`null` = 全部。
- `grain`：`day|week|month`；`range` 与 `from/to` 二选一（同时给以 `from/to` 为准）。

### 6.2 `GET /overview/summary`

```json
{
  "window": { "from": "2026-10-12", "to": "2026-11-11", "grain": "day" },
  "totals": { "badCases": 128, "self": 74, "discovery": 54,
              "sessions": 31, "pendingSessions": 2, "sources": 9 },
  "quota": { "used": 128, "quota": 500 },
  "byObject": [ { "object": "deep-research", "total": 42, "self": 30, "discovery": 12 } ]
}
```

- `byObject` 供来源分布使用（top6 由前端截断），按 `total` 降序；`objects` 筛选时该数组只含选中来源。
- `sessions` = 去重根会话数；`pendingSessions` 见 §2.1。

### 6.3 `GET /overview/trend`

```json
{
  "window": { "from": "2026-10-12", "to": "2026-11-11", "grain": "week" },
  "buckets": [
    { "bucket": "2026-W42", "label": "10/12 – 10/18", "self": 6, "discovery": 3,
      "byObject": [ { "object": "deep-research", "self": 4, "discovery": 2 } ] },
    { "bucket": "2026-W43", "label": "10/19 – 10/25", "self": 0, "discovery": 0, "byObject": [] }
  ]
}
```

- 桶序列由服务端补齐（含全 0 桶）；`label` 由服务端给（日 `10-12`、周 `10/12 – 10/18`、月 `2026-10`），前端不做日期运算。
- `byObject` 只含选中来源；`objects` 为空时含全部来源（前端做矩阵与分布）。
- 响应体积预算：366 天日粒度 × 50 来源 ≈ 18k 行，超出前端可用性；因此 **`grain=day` 且时间窗 > 92 天时服务端强制降级为 `week`** 并在 `window.grain` 返回实际粒度（前端提示「已按周展示」）。

### 6.4 `GET /overview/sources`

```json
{ "items": [ { "object": "deep-research", "total": 42, "self": 30, "discovery": 12, "sessions": 18 } ] }
```

按 `total` 降序；`sessions` 是该来源的关联去重 Session 数（与对象视角的「关联 Session」不同：后者要求对象在该 Session 出现过）。

### 6.5 `GET /bad-cases`（组合筛选分页列表）

```json
{
  "items": [
    { "badCaseId": "BC-HC-0001", "sessionId": "cb819c5b-…", "sessionTitle": "AI agent + 视频播放…",
      "objectName": "deep-research", "objectType": "skill", "objectVersion": "v2.0.0",
      "badCaseType": "self", "title": "检索索引读取失败",
      "createdAt": "2026-11-11T10:20:30+08:00", "attributionCount": 3 }
  ],
  "total": 128, "page": 1, "pageSize": 8
}
```

- `attributionCount` = 该 bad case 的去重「对象·版本」归因数（`COUNT(DISTINCT object_type, object_name, object_version)`），前端列表直接显示「3 条归因」。
- `sessionTitle` 来自 `session_families`（未归一化时为 `null`，前端显示 Session ID 前 8 位）。

### 6.6 `GET /overview/targets`（对象列表 + 汇总）

```json
{
  "summary": { "targets": 6, "sessions": 24, "potential": 63, "attributed": 28, "nonTarget": 9, "unanalyzed": 26 },
  "items": [
    { "targetId": "tgt-123", "objectType": "skill", "objectName": "deep-research",
      "defaultRef": "v2.0.0", "enabled": true,
      "sessions": 18, "potential": 42, "attributed": 20, "nonTarget": 6, "unanalyzed": 16,
      "evolvable": 36 }
  ],
  "total": 6, "page": 1, "pageSize": 5
}
```

- 排序：`evolvable DESC, potential DESC, objectName ASC`。
- `summary` 的去重口径：`sessions` 为所有对象关联 Session 的并集去重；`potential`/`attributed`/`nonTarget`/`unanalyzed` 为按 bad case 去重（同一 bad case 对多个对象潜在时只计一次，`unanalyzed` 同）。

### 6.7 `GET /overview/targets/trend`

```json
{
  "window": { "from": "2026-10-12", "to": "2026-11-11", "grain": "day" },
  "buckets": [
    { "bucket": "2026-11-11", "label": "11-11",
      "attributed": 4, "nonTarget": 1, "unanalyzed": 2,
      "byTarget": [ { "targetId": "tgt-123", "attributed": 3, "nonTarget": 0, "unanalyzed": 1 } ] }
  ]
}
```

- `targets` 多选（空 = 全部启用对象）；`states` 多选（`isTarget|nonTarget|unanalyzed`，空 = 三者全显示）只控制堆叠信息。
- 时间桶按**归因生成时间**（attributions.updated_at）与上报时间双轴对齐：`attributed/nonTarget` 用归因时间落桶，`unanalyzed` 用 `bad_cases.created_at` 落桶（未归因的 bad case 没有归因时间）。该差异写进响应说明字段 `meta.bucketPolicy`，前端 tooltip 展示。

### 6.8 `GET /overview/targets/cases`（潜在 bad case 列表）

```json
{
  "items": [
    { "badCaseId": "BC-HC-0007", "objectType": "skill", "objectName": "deep-research",
      "objectVersion": "v2.0.0", "source": "deep-research", "state": "attributed",
      "badCaseType": "self", "title": "检索索引读取失败",
      "createdAt": "2026-11-09T15:02:00+08:00", "sessionId": "cb819c5b-…",
      "attributionId": "AT-…", "category": "error" }
  ],
  "total": 63, "page": 1, "pageSize": 8
}
```

- `state ∈ attributed|non_target|unanalyzed`；`attributionId` 仅在 `attributed|non_target` 时非空，前端据此渲染归因报告 ID 链接（落到 `?case=&tab=attr&at=`）。
- 筛选：`targets[]`、`objects[]`（上报来源）、`states[]`、`from/to`；分页 8。
- 排序固定 `created_at DESC`。

### 6.9 `GET /overview/targets/{targetId}/detail`

```json
{
  "target": { "targetId": "tgt-123", "objectName": "deep-research", "defaultRef": "v2.0.0" },
  "stats": { "sessions": 18, "potential": 42, "distinctCases": 31, "versions": 5 },
  "byVersion": [
    { "version": "v2.0.0", "potential": 14, "attributed": 6, "nonTarget": 2, "unanalyzed": 6 }
  ],
  "bySource": [
    { "source": "deep-research", "total": 20, "distinct": 14 },
    { "source": "code-review", "total": 11, "distinct": 9 }
  ]
}
```

- `versions` 参数（多选，空 = 最近 `versionLimit` 个，默认 5）；版本排序按 semver 降序，非 semver 按字符串降序。
- `byVersion` 的三态之和可大于 `potential`（同一 bad case 多版本口径，§4）；`bySource` 的 `total` 未去重、`distinct` 去重后（原型括号内数字）。

### 6.10 `GET /sessions`

```json
{
  "items": [ { "id": "cb819c5b-…", "short": "…", "title": "…", "repo": "llm-wiki",
               "model": "glm-5.3", "startedAt": "2026-09-05T17:17:53+08:00",
               "durationSeconds": 63420, "status": "partial", "skills": ["deep-research"],
               "stats": { "userTurns": 12, "messages": 1103, "tools": 197, "errors": 4,
                          "agents": 57, "badCases": 3, "tokens": 58368517,
                          "failPer100Messages": 0.36, "badCasesPer100Messages": 0.27 } } ],
  "total": 31, "pendingSessions": 2
}
```

- 结构 = V1 `SessionListItem` + `total/pendingSessions`；`stats` 口径不变（[05 §3.1](05-api-design.md)）。
- 空间过滤：`session_families.id IN (SELECT DISTINCT bad_case_session_id FROM bad_cases WHERE workspace_id=:wid)`；`total` 为该集合按 `q/status` 过滤后的计数。

### 6.11 端点校验矩阵

| 端点 | 权限 | 分页 | 必填 | 关键校验 | 主要错误码 |
|---|---|---|---|---|---|
| `…/overview/summary` | viewer | 无 | — | `from ≤ to`、窗口 ≤366 天、`objects` ≤50 | `WINDOW_INVALID` `OBJECT_FILTER_TOO_LARGE` |
| `…/overview/trend` | viewer | 无 | — | 同上 + `grain ∈ {day,week,month}` | `GRAIN_INVALID` `WINDOW_INVALID` |
| `…/overview/sources` | viewer | 无 | — | 同 summary | 同上 |
| `…/bad-cases` | viewer | 8/页 | — | 三个筛选均可空；`badCaseType ∈ {self,discovery}` | `VALIDATION_INVALID` |
| `…/overview/targets` | viewer | 5/页 | — | 无 | `WINDOW_INVALID` |
| `…/overview/targets/trend` | viewer | 无 | — | `targets` 均为本空间启用对象；`states` 子集校验 | `VALIDATION_INVALID` |
| `…/overview/targets/cases` | viewer | 8/页 | — | `states ⊆ {isTarget,nonTarget,unanalyzed}` | `VALIDATION_INVALID` |
| `…/overview/targets/{id}/detail` | viewer | 无 | `id` 存在且属于本空间 | `versions` ≤20；`versionLimit ∈ {5,10,20,0}` | `TARGET_NOT_FOUND` |
| `…/sessions` | viewer | `limit` 默认 10 | — | `q ≤512`；`status/sort` 封闭集合 | `VALIDATION_INVALID` |

- 权限列全部是「最低角色」；空间可见性由依赖统一处理（不可见 → 404）。
- 分页端点 `page ≥ 1`、`pageSize` 受端点上限约束（列表 8、对象 5），超限 422；页码越界返回最后一页。
- 时间参数二选一：`range=7|30|90` 或 `range=0&from=&to=`；同时给 `range` 与非空 `from/to` 时以 `from/to` 为准且不再校验 range 取值。

### 6.12 新增错误码

| code | HTTP | 场景 |
|---|---|---|
| `GRAIN_INVALID` | 422 | `grain` 不在 `day|week|month` |
| `WINDOW_INVALID` | 422 | `from > to`，或窗口 > 366 天，或 `range=0` 缺 `from/to` |
| `OBJECT_FILTER_TOO_LARGE` | 422 | `objects` 超过 50 项 |

## 7. 服务端实现

### 7.1 模块与文件

| 改动 | 文件 | 内容 |
|---|---|---|
| 新增服务 | `app/service/overview/schemas.py` | `OverviewSummary`/`TrendBucket`/`SourceRow`/`BadCaseListItem`/`TargetOverview`/`TargetDetail` 等 DTO |
| 新增服务 | `app/service/overview/service.py` | `OverviewService`：口径组装、时间桶、来源聚合、对象视角编排、缓存读写 |
| 新增仓储 | `app/db/crud/overview.py` | 聚合 SQL（`count_by_type`、`trend_by_bucket`、`sources`、`bad_case_page`、`session_page`、`pending_sessions`） |
| 复用 | `service/evolution/potential.py`（[17 §4](17-v2-attribution.md)） | 对象视角的关联 Session / 潜在匹配，不新写一套 |
| 复用 | `db/crud/attributions.py`（[17 §5](17-v2-attribution.md)） | 三态计数、版本分布、来源分布 |
| 新增路由 | `app/api/overview.py` | §6 端点，全部挂空间角色依赖 |
| 既有路由 | `app/api/sessions.py` | 新增 `/api/workspaces/{workspaceId}/sessions` 变体（复用 `SessionService`，加 `workspace_id` 过滤与 `total/pendingSessions`） |
| 装配 | `app/main.py` | `app.state.overview = OverviewService(...)` |
| fixtures | `fixtures/` | 空间化样例覆盖「多来源 × 多类型 × 多周」以便图表有形状 |

### 7.2 查询形态（聚合 SQL）

```sql
-- summary：一次拿总数 + 类型分布 + 去重会话数
SELECT COUNT(*)                                    AS bad_cases,
       SUM(CASE WHEN bad_case_type='self' THEN 1 ELSE 0 END)      AS self_count,
       SUM(CASE WHEN bad_case_type='discovery' THEN 1 ELSE 0 END) AS discovery_count,
       COUNT(DISTINCT bad_case_session_id)          AS sessions,
       COUNT(DISTINCT object_name)                  AS sources
FROM bad_cases
WHERE workspace_id = :wid AND created_at >= :from AND created_at < :to_plus_one;

-- trend：方言分桶（repository 适配器各自实现，服务层不含方言字符串）
--   MySQL : DATE_FORMAT(created_at, '%Y-%m-%d') / YEARWEEK(created_at, 3) / DATE_FORMAT(created_at, '%Y-%m')
--   SQLite: strftime('%Y-%m-%d') / strftime('%Y-%W') / strftime('%Y-%m')
SELECT :bucket_expr AS bucket, object_name, bad_case_type, COUNT(*) AS n
FROM bad_cases
WHERE workspace_id = :wid AND created_at >= :from AND created_at < :to_plus_one
  AND (:objects_empty OR object_name IN :objects)
GROUP BY bucket, object_name, bad_case_type
ORDER BY bucket;
```

- 服务层把 `(bucket, object, type) → n` 折叠成 `buckets[]`，并按窗口生成空桶——**不依赖 DB 生成序列**（SQLite 无 `generate_series`，MySQL 8 也要 `WITH RECURSIVE`，两端收益都不大）。
- 列表分页：`LIMIT :pageSize OFFSET (:page-1)*:pageSize` + 一次 `COUNT(*)`；`attributionCount` 用 `LEFT JOIN (SELECT bad_case_id, COUNT(DISTINCT …) …)` 子查询一次带回，避免 N+1。
- `total` 与 `items` 必须在同一快照内（同一事务/只读会话），避免分页错位。

### 7.3 对象视角的批量计算与缓存

对象视角的成本集中在「每个对象的关联 Session + 潜在匹配」，逐个对象各跑一遍 `PotentialMatcher`：

```text
GET /overview/targets（一页 5 个对象）
  for target in page:
      key = (wid, target.id, defaultRef?, from, to, policy_version)
      hit = cache.get(key)                     # 60s TTL，进程内 LRU（容量 512）
      if hit: use
      else:
          sessions = matcher.associated_sessions(target, wid, from, to)   # 1 次 SQL：对象触发点 + bad case 会话集合
          potential = matcher.potential_cases(target, sessions, policy)   # 1 次 SQL：会话内 bad case + 触发点
          cache.set(key, result)
  # 三态计数：attributions 批量查询（WHERE workspace_id AND object_name IN (...) AND object_version IN (...))
```

- 每个对象 2 次 SQL + 1 次批量归因查询；5 个对象 ≈ 11 次查询，总耗时目标 < 300ms（本地 SQLite）/ < 200ms（MySQL，索引命中）。
- 缓存失效：上报写入后清 `(wid, *)`；targets 配置变更后清该对象；`policy_version` 变化自然换 key。
- 多实例部署时缓存各自维护，60 秒内可能读到旧值——总览是展示型页面，可接受；要强一致时关缓存（配置项）。

### 7.4 Session 列表的 total 与投影

```sql
-- 空间 Session 集合（视图化查询，不建物化表）
WITH ws_sessions AS (
  SELECT DISTINCT bad_case_session_id AS id FROM bad_cases WHERE workspace_id = :wid
)
SELECT f.* FROM session_families f JOIN ws_sessions s ON s.id = f.id
WHERE (:q = '' OR f.search_text LIKE :like OR f.id LIKE :id_like)
  AND (:status = 'all' OR f.status = :status OR (:status = 'problem' AND f.status IN ('partial','fail')))
ORDER BY f.started_at DESC
LIMIT :limit;

-- pendingSessions：空间 bad case 会话数 - 已归一化交集
SELECT COUNT(*) FROM (
  SELECT DISTINCT bad_case_session_id AS id FROM bad_cases WHERE workspace_id = :wid
) s LEFT JOIN session_families f ON f.id = s.id WHERE f.id IS NULL;
```

- `search_text` 已在归一化时 lower 拼接；`q` 先 lowercase 再 LIKE（与 V1 一致）。
- 投影查询在 10⁴ bad case / 10³ session 量级下单次 < 20ms（`INDEX(workspace_id, created_at)` + `session_families` 主键 JOIN）。

### 7.5 索引与执行计划核对（交付前必做）

| 查询 | 期望访问路径 | 失败信号 |
|---|---|---|
| summary 计数 | `bad_cases` 走 `INDEX(workspace_id, created_at)` range scan + filesort 无 | `Using temporary` 出现在 EXPLAIN 的 Extra |
| trend 分组 | 同上 + 临时表聚合（可接受） | 全表扫描（`type=ALL`） |
| 列表分页 | 同上 + `LIMIT` 早停 | `Using filesort` 且行数 > 分页量级（说明排序键没进索引） |
| 三态计数 | `bad_case_attributions` 走 `INDEX(workspace_id, object_name, object_version)` | 命中 `INDEX(workspace_id, updated_at)` 却在按 object 过滤 |
| Session 投影 | `bad_cases` 的 `INDEX(workspace_id, created_at)` + `session_families` PK | `DISTINCT` 后回表行数 ≈ 全表 |

- 交付验收要求附一次 `EXPLAIN` 输出（MySQL 8 与 SQLite `EXPLAIN QUERY PLAN`），与上表逐条对照。
- 若某条查询计划不符：优先补索引，其次改查询形态（先按空间取 id 集合再 JOIN），**不加物化表**（§10 非目标）。

## 8. 前端

### 8.1 路由与 URL 状态

见 §1.1；额外约定：

- `?objects=` 用逗号分隔的来源名（URL 可读，便于分享），`?targets=` 用 targetId，`?states=` 用 `isTarget,nonTarget,unanalyzed`。
- 切换 Tab 不重置 `range/grain/from/to`；切换空间重置全部（含 Tab → `cases`）。
- 刷新恢复：从 URL 解析筛选 → 与 store 的 `currentWorkspaceId` 校验 → 不匹配则重定向（[15 §6.2](15-v2-workspaces.md)）。

### 8.2 组件树

```text
pages/overview/
├── Index.vue                    # Tab 壳 + 共享筛选条 + 空态路由
├── components/
│   ├── StatStrip.vue            # 6 格指标（数字用 tabular-nums）
│   ├── FilterBar.vue            # 时间/粒度/来源多选（受控，写 URL）
│   ├── SourceMultiSelect.vue    # 搜索 + 多选 + chip 移除 + 全选
│   ├── StackedBucketChart.vue   # 自研 SVG 堆叠柱图（复用 V1 蓝/紫 token）
│   ├── SourceBars.vue           # 来源分布条（top6 + 其余折叠）
│   ├── SourceMatrix.vue         # 来源 × 时间桶矩阵（可折叠）
│   ├── BadCaseTable.vue         # 列表 + 分页（8/页）+ 空态
│   ├── TargetsOverview.vue      # 对象统计条 + 趋势 + 两块分布
│   ├── TargetSideList.vue       # 5/页对象侧栏（可进化排序 + 增编删入口）
│   ├── TargetDetailCard.vue     # 单对象分析卡（对象/版本多选 + 独立时间窗）
│   └── PotentialCaseTable.vue   # 潜在 bad case 列表（8/页 + 三态滤镜）
└── composables/…
```

- 图表不引第三方库：`StackedBucketChart` 用 SVG `rect` + 自定义刻度（V1 原型同款实现），保持视觉一致且不增加 bundle。
- 表格复用 `components/ui/` 的 `DataTable`（若 V1 未抽，则本页先内联，其他页复用前先抽）。

### 8.3 composables

```ts
// useOverview.ts
useOverviewSummary(wid: Ref<string>, filters: Ref<OverviewFilters>)
useOverviewTrend(wid, filters)          // 数据直接驱动 StackedBucketChart
useOverviewSources(wid, filters)
useOverviewBadCases(wid, filters)       // 分页：page 在 filters 里
useOverviewTargets(wid, filters)        // 侧栏 + 汇总
useOverviewTargetTrend(wid, filters)
useOverviewPotentialCases(wid, filters)
useTargetDetail(wid, targetId, filters)
```

- `filters` 必须是 `ref/computed`（V1 踩过的坑：传普通对象会冻结成首帧快照）。
- 趋势与列表分别 `staleTime: 30s`；对象视角 `staleTime: 60s`（与服务端缓存对齐）。
- 请求取消：`AbortController` 由 vue-query 传入，切换筛选时自动取消上一个请求。

### 8.4 三态与错误

| 状态 | 表现 |
|---|---|
| 加载 | 图表骨架（灰块占位）+ 列表 4 行骨架；不整页 spinner |
| 空 | 图表区空态文案 + 「清除筛选」；列表空态；对象视角无对象时给「去配置进化对象」 |
| 错误 | 区块级 `ErrorState`（错误码 + 重试）；`404 WORKSPACE_NOT_FOUND` 整页跳空间选择 |
| 422（筛选非法） | 筛选条标红 + 顶部条提示（如窗口 > 366 天） |

## 9. 测试

| 层 | 用例（摘要） |
|---|---|
| 口径单测 | summary 各字段与手算 SQL 一致；空桶补零；跨年 ISO 周标签；`pendingSessions` 正确 |
| 趋势单测 | 日/周/月分桶边界（月首、周一、跨年）；> 92 天强制降级 week 并回传实际粒度 |
| 对象视角 | 潜在数与向导预览同条件一致（shared matcher 回归）；三态计数去重；版本口径可重复计数并 `distinctCases` 去重 |
| 列表 | 组合筛选（时间/来源/类型任意为空）；分页越界回最后一页；`attributionCount` 去重正确 |
| Session 列表 | 默认 10 条 + total；`q` 三类匹配；未归一化计入 pending；跨空间 404 |
| 性能 | 10⁴ bad case / 10³ session 下 summary+trend+list 三请求 P95 < 500ms（SQLite 基准）；对象视角 5 个对象 < 300ms |
| 前端 | 图表刻度算法（1/2/5×10ⁿ）；筛选写 URL 可恢复；切空间整树失效 |
| E2E | 上报 → 总览数字变化 → 下钻到错误详情并选中对应 bad case |

门禁：`pnpm test:api`、`pnpm test:web`、`pnpm test:e2e -- --pattern "overview"`。

## 10. 非目标

- 自定义图表类型（折线/饼图切换）、导出 CSV / 图片。
- 总览数据的物化/预聚合表（量级未到；60s 缓存先行）。
- 跨空间汇总视图（全局管理员也按空间逐个看）。
- 「查看信息」三态过滤联动分布块（原型第十四轮已定为只过滤趋势图）。
- 自定义指标（分母/口径配置）、告警阈值。

## 11. 已确认决策

| # | 决策 | 依据 |
|---|---|---|
| O1 | 空间 Session 集合 = bad case 投影，不物化、不加轨迹侧空间列 | [15 W2]；与原型 used 统计口径一致 |
| O2 | 潜在 bad case 口径在总览/向导/run 三处共用同一实现 + 60s 缓存 | 口径漂移会被直接对比发现 |
| O3 | Session 列表默认 limit 10 + 响应加 total/pendingSessions；搜索回车触发 | 目标态第 5 点；保留 q 三类匹配语义 |
| O4 | 趋势按 `created_at` 分桶、ISO 周、Asia/Shanghai；分桶 SQL 走方言适配 | 上报时间是最直观的业务时间轴 |
| O5 | 下钻 = 行内 ID 深链（新窗口），整行不可点 | 原型第十七轮决策，防误触 |
| O6 | 总览二级 Tab 只做 bad case / 进化对象两个视角 | 原型验收范围；不扩图表种类 |
| O7 | 日粒度窗口 > 92 天时服务端强制降级为周并回传实际粒度 | 366×50 的日粒度矩阵不可读也不可传 |
| O8 | `attributed/nonTarget` 按归因时间落桶、`unanalyzed` 按上报时间落桶，响应声明 `bucketPolicy` | 未归因的 bad case 没有归因时间；口径差异必须显式 |
| O9 | 对象视角逐对象跑 matcher + 进程内 60s LRU，失效由写路径触发 | 复用同一实现优先于造专用近似 SQL |
