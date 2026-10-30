# 12 · bad_cases 目录数据定时同步

> 本文回答：bad_cases 如何从上游分页查询接口定时增量同步进本库、游标与统计如何维护、已存在记录如何更新、前端在哪里展示。
> 前置：[04 后端架构](04-backend-architecture.md) · [05 接口设计](05-api-design.md) · [06 数据库设计](06-database-design.md) · [07 后端实现](07-backend-implementation.md) · [08 前端实现](08-frontend-implementation.md) · [11 根会话轨迹定时同步](11-bad-case-session-sync.md)。
> 状态：设计已确认（2026-10-30），待原型截图确认后实施。

## 1. 背景与目标

`bad_cases` 目前被当作"数据库里已经存在"的既有数据：本服务只读，外部归因/上报系统直写同库；开发期由 fixtures 灌演示数据。问题列表、错误详情、归因分析和 [11 章](11-bad-case-session-sync.md) 的根会话轨迹补齐都建立在这个前提上。上游改为独立分页查询接口后，本服务必须自己把 bad_cases 拉进表里，否则整条问题链路没有数据来源。

本特性新增一条目录同步路径：定时任务按 `bad_case_id` 游标调用上游分页接口，逐页把坏例写入 `bad_cases`；已存在的 `bad_case_id` 不新增行，而是用上游字段更新该行。同步状态表记录游标、已同步数量、上游未同步数量与最后一次运行结果；前端在现有"数据同步"浮层里展示。

目标：

- 不依赖人工触发，定时增量拉取上游坏例并写入 `bad_cases`。
- 按 `bad_case_id` 幂等：新 id 插入，已存在 id 更新全部上游字段，不产生重复行。
- 游标与数据同事务推进；进程重启或任务失败后从上一个已提交页继续。
- 任务单飞、串行，不并发调用上游。
- 前端可见已同步/未同步数量与同步中/失败/未配置状态。

非目标：

- 不处理上游删除，不做行删除或墓碑同步。
- 不检测旧 id 的内容变更：接口只返回 `id > cursor`，游标之后无法再触达；`updated_at` 变化不触发重拉。
- 不替换 [11 章](11-bad-case-session-sync.md) 的轨迹补齐，不改其状态表与语义。
- 不在 CI 调用真实上游。

## 2. 数据流与组件

```text
上游分页查询接口
   │ GET ?bad_case_id=<cursor>&offset=0&limit=<page_size>
   ▼
BadCaseCatalogQuerySource（严格模型、串行、超时/重试）
   ▼
BadCaseCatalogSyncService
   ├─ 读 bad_case_catalog_sync 游标
   ├─ 单事务：逐条 upsert bad_cases + 更新状态表
   └─ 循环到空页 / 预算耗尽
   ▼
GET /api/acquisition/status → badCaseCatalogSync 统计
   ▼
TopNav 数据同步浮层
```

组件归属：

| 组件 | 位置 | 职责 |
|---|---|---|
| `BadCaseCatalogQuerySource` | `apps/api/app/third_party_api/bad_case_query/` | 分页查询 HTTP 适配、严格响应模型、错误映射、串行锁 |
| `BadCaseCatalogSyncService` | `apps/api/app/service/acquisition/bad_case_catalog_sync.py` | 游标分页、upsert、状态推进、预算控制 |
| `BadCaseCatalogSyncCoordinator` | `apps/api/app/service/acquisition/bad_case_catalog_sync_coordinator.py` | 启动即跑、定时循环、单飞跳过、状态聚合 |
| `BadCaseCatalogSyncRepository` | `apps/api/app/db/crud/bad_case_catalog_sync.py` | 状态表读写、upsert、计数 |
| 路由 | `apps/api/app/api/acquisition.py` | 扩展 `GET /api/acquisition/status`；不新增写接口 |
| 前端 | `apps/web/src/components/layout/TopNav.vue`、`utils/syncStatus.ts` | 浮层新增一行与状态文案 |

## 3. 外部查询服务契约

### 3.1 请求

```http
GET {base}/bad-cases?bad_case_id=<int>&offset=<int>&limit=<int>
Authorization: Bearer <service-token>
Accept: application/json
```

| 参数 | 必填 | 约束 | 语义 |
|---|---|---|---|
| `bad_case_id` | 是 | 非负整数 | 只返回 id 严格大于该值的记录，按 id 升序 |
| `offset` | 否 | ≥ 0，默认 0 | 分页偏移；同步固定传 0（见 §4.1） |
| `limit` | 否 | 1–200，默认 20 | 页大小 |

真实服务 path 与鉴权形式尚未提供，adapter 内按可配置常量处理；真实值确定后只改适配层，不改业务层。

### 3.2 响应

```json
{
  "total": 42,
  "offset": 0,
  "limit": 200,
  "items": [
    {
      "bad_case_id": 128,
      "bad_case_session_id": "cb819c5b-...",
      "bad_case_type": "self",
      "object_name": "deep-research",
      "object_type": "skill",
      "object_version": "v2.0.0",
      "bad_case_agent_id": null,
      "bad_case_title": "检索索引读取失败",
      "bad_case_description": "完整描述正文…",
      "meta_data": {"source": "manual"},
      "source": "upstream",
      "created_at": "2026-10-30T10:00:00+08:00",
      "updated_at": "2026-10-30T10:00:00+08:00"
    }
  ]
}
```

- `total`：满足 `bad_case_id > 参数` 的记录总量；`offset`/`limit` 不改变它。
- `offset`/`limit`：服务端回显；同步校验回显值与请求一致。
- `items`：按 id 升序；上游口径是"最多 `limit` 条"，即 `min(total - offset, limit)`。需求描述里写作 `max(...)`，按数学语义应为笔误；客户端不依赖该公式，只校验 `len(items) <= limit`、id 严格递增且都大于请求游标。

字段映射（其余字段同名直写）：

| 接口字段 | 表列 | 处理 |
|---|---|---|
| `bad_case_id` | `bad_cases.bad_case_id` | 接口是整数，落库转十进制字符串 |
| `bad_case_title` | `bad_cases.title` | 唯一改名映射 |
| `object_name` | `bad_cases.object_name` | 为空时依次取 `source`、`unknown` |
| `object_type` | `bad_cases.object_type` | 为空时取 `skill` |
| `created_at` / `updated_at` | 同名 | 可选；存在时解析 ISO-8601 带时区时间并按原值写入，缺失时用本次同步时间兜底 |

### 3.3 校验、错误与串行

- 严格模型：`extra="forbid"`，缺必填字段、类型不符、id 非递增、页大小超限、`total < len(items)` 都记为 `BAD_CASE_QUERY_INVALID_RESPONSE`。
- 时间戳字段可以缺失：`bad_cases.created_at` / `updated_at` 是 NOT NULL，缺失时用本次同步时间兜底，不判非法；存在但不是带时区 ISO-8601 才算响应非法。
- 4xx 不重试；401/403 → `BAD_CASE_QUERY_UNAUTHORIZED`；429/5xx/超时按配置重试；重试耗尽 → `BAD_CASE_QUERY_TIMEOUT` / `BAD_CASE_QUERY_REQUEST_FAILED`。
- `BadCaseCatalogQuerySource` 内部用一把 `asyncio.Lock` 包住每次请求；即使未来有第二个调用方，也不会并发。
- 响应体上限 8 MiB（200 条足够），超限按非法响应处理。

## 4. 游标、分页与冷启动

### 4.1 游标式翻页（推荐）

同步不按 offset 翻页，而是每页都把 `offset` 固定为 0，用"本页最大 id"推进游标：

```text
cursor = state.last_bad_case_id
loop:
    page = GET ?bad_case_id=cursor&offset=0&limit=page_size
    if page.items is empty: break
    max_id = max(item.bad_case_id for item in page.items)
    if max_id <= cursor: invalid response
    transaction:
        upsert all page.items
        state.last_bad_case_id = max_id
        state.pending_count = max(page.total - len(page.items), 0)
        state.synced_count = COUNT(bad_cases)
        state.updated_at = now
    cursor = max_id
```

理由：

- 每页独立可重入：崩溃后从最后提交的游标继续，不会跳页或重复消费。
- 新记录只会追加在 id 更大处，不会让已读页漂移。
- `total` 随游标前移而变小，天然表达"还剩多少条"。

停止条件：空 `items`、`total == 0`、达到 `max_pages_per_run` 或时间预算。预算耗尽不算失败，状态回到 `idle`，下次 tick 继续。

### 4.2 冷启动：状态表为空

| 方案 | 做法 | 代价 |
|---|---|---|
| A. 从本库最大 id 开始 | 状态表无行时取 `bad_cases` 中最大的纯数字 id，空表取 0 | 不重拉存量；首轮只拉新增 |
| B. 从 0 开始全量重拉（已确认） | 游标从 0 起，逐页 upsert 存量 | 首轮接口调用量等于存量条数，但会刷新全部旧行 |

已确认选 B：状态表无行时游标从 0 开始，首轮把存量整体重拉一遍，命中已有 `bad_case_id` 的行按 §5 更新。页大小、最大页数与时间预算把首轮摊到多个 tick，`pending_count` 持续显示剩余量。这样"已存在则更新"从上线首轮起就是真实路径，而不是只在重试时才会走到。

### 4.3 已存在记录的更新

upsert 是唯一写路径：`bad_case_id` 命中则更新 §3.2 的全部字段，不新增行，不触碰 `bad_case_analysis`、`probe_reports` 等关联表。更新路径在以下场景真实发生：

- 首次部署（状态表无行、游标从 0）时全量刷新存量。
- 同一页因失败回滚后重试（理论上同页重复提交）。
- 人工重置状态表游标后的重放。

游标只增不减；任何情况下不把 `last_bad_case_id` 写小。

## 5. 写入：upsert 与事务

### 5.1 方言实现

| 方言 | 语句 |
|---|---|
| SQLite | `insert(bad_cases).on_conflict_do_update(index_elements=["bad_case_id"], set_=...)` |
| MySQL | `insert(bad_cases).on_duplicate_key_update(...)` |

仓储按 `database.dialect` 分支，业务层只调用 `upsert_many(rows)`。每页一次批量语句，不做逐行 select-then-write，避免与外部写入方竞态。

### 5.2 事务边界

- 一页 = 一个事务：`upsert_many` + 状态表更新（游标、计数、时间）同事务提交。
- 页内任一条失败 → 整页回滚，游标不动，状态记 `failed` 与稳定错误码；下次从同一游标重试。
- 不使用部分成功：避免"数据进了表、游标没动"导致重复拉取，或"游标动了、数据没进"导致永久空洞。
- 任务结果记录 `pages`、`inserted`、`updated`、`lastBadCaseId`。

### 5.3 与外部写入方共存

`bad_cases` 可能仍有外部系统直写。本特性的 upsert 只覆盖上游接口返回的字段，按主键合并；不做全表删除、不做 `TRUNCATE`。若上游接口删除了记录，本服务保留该行（见非目标）。

## 6. 状态表与统计

### 6.1 `bad_case_catalog_sync`（单行）

| 列 | 类型 | 约束 | 语义 |
|---|---|---|---|
| `id` | `VARCHAR(16)` | PK | 固定值 `bad_cases`，保证单行 |
| `last_bad_case_id` | `BIGINT` | NOT NULL | 已提交的最大 bad_case_id 游标 |
| `synced_count` | `INTEGER` | NOT NULL | 最近一次提交时 `COUNT(bad_cases)` |
| `pending_count` | `INTEGER` | NOT NULL | 最近一页计算出的上游剩余数量 |
| `status` | `VARCHAR(16)` | NOT NULL | `idle` / `running` / `failed` |
| `attempts` | `INTEGER` | NOT NULL | 连续失败次数，成功后清零 |
| `last_error` | `TEXT` | NULL | 稳定错误码，不存上游正文 |
| `last_run_at` | `DATETIME` | NULL | 最近一次开始时间 |
| `last_success_at` | `DATETIME` | NULL | 最近一次成功提交时间 |
| `updated_at` | `DATETIME` | NOT NULL | 行更新时间 |

`unavailable` 不入库，由"查询服务未配置"实时派生。SQLite 用 `INTEGER`，MySQL 用 `BIGINT`（`with_variant`），与现有计数列一致。

### 6.2 计数口径

- `synced` = `COUNT(bad_cases)`，包含历史已有行；语义是"我们表里现在有多少条坏例"。
- `unsynced` = 最近一页的 `total - len(items)`，即游标之后上游还剩多少条；一轮拉完后为 0。
- 状态接口的 `lastBadCaseId` 直接返回游标，便于排查。
- 首次部署从 0 全量重拉时，`synced` 随每页提交增长，`unsynced` 是上游剩余量；拉完后 `synced` 等于表内总行数、`unsynced` 为 0。

### 6.3 状态机与启动恢复

```text
idle ──trigger──▶ running ──success──▶ idle
                    │
                    └──failure──▶ failed ──next tick──▶ running
```

- 启动时若状态是 `running` 但没有活跃 job（上次进程崩溃），把状态复位为 `failed`，`last_error = BAD_CASE_CATALOG_SYNC_INTERRUPTED`，随后立即触发一次。
- `attempts` 连续失败累加，成功后清零；不做指数退避，按同步间隔重试，避免状态表再维护一套重试时间。
- 多实例不在交付范围：`JobRunner` 是进程内全局串行；跨进程需要额外锁，本设计不阻碍后续增加。

### 6.4 归因分析整体统计（只读）

浮层里的"归因分析"不实现归因流程，只读 `bad_case_analysis` 汇总整体进度：

- `total = COUNT(bad_cases)`：问题总量。
- `issue = COUNT(analysis_status='analyzed_issue')`；`nonIssue = COUNT(analysis_status='analyzed_nonissue')`。
- `analyzed = issue + nonIssue`：已给出结论（是问题或非问题）的数量。
- `pending = max(total - analyzed, 0)`：没有分析行或仍是 `unanalyzed` 的数量。
- 统计只 JOIN `bad_cases` 计数，避免外部写入绕过外键时把孤儿归因行算进来。
- 每次轮询两条 `COUNT` 查询，走 `ix_bad_case_analysis_status` 与主键，不新增物化列。

## 7. 调度与单飞

- job kind：`bad_case_catalog_sync`，由 `JobRunner` 执行，天然串行。
- 启动顺序：`jobs.recover()` → 目录同步 coordinator `start()`（复位残留状态并立即 `run_once()`）→ 定时循环。
- "启动时如果上一次已经处理好了就开始执行"：`start()` 不等待首个 interval，直接触发一次；若已有活跃 job 则跳过。
- 定时循环：每 `interval` 秒触发；若 `find_active_kind` 存在活跃 job，直接跳过并记日志，不排队、不取消。
- 无新增数据（`total == 0` 或空页）时 job 仍会跑一次，但只发一次请求；也可在触发前用状态表的 `pending_count` 短路，设计上允许，实现以"一次请求确认"为准。
- 未配置查询服务时不注册触发（`unavailable`），不影响现有 scheduler。

## 8. API 与前端

### 8.1 扩展 `GET /api/acquisition/status`

在 m6-15 已加的 `badCaseSync` 旁增加：

```json
{
  "badCaseCatalogSync": {
    "synced": 120,
    "unsynced": 8,
    "lastBadCaseId": 128,
    "status": "running",
    "lastRunAt": "2026-10-30T16:00:00+08:00",
    "lastError": null
  },
  "badCaseAnalysis": {
    "total": 136,
    "analyzed": 96,
    "pending": 40,
    "issue": 58,
    "nonIssue": 38
  }
}
```

- `status` ∈ `unavailable | idle | running | failed`；`queued` 可沿用 job 状态，前端统一映射。
- `lastError` 只返回稳定 code。
- 两个字段与 `badCaseSync` 并列，避免新增轮询端点。

### 8.2 前端浮层

浮层固定四段，顺序为 **问题数量 → 问题轨迹 → 会话归一化 → 归因分析**：

```text
数据同步
问题数量      总 136 · 已同步 128 · 未同步 8
              空闲 · 游标 #128
问题轨迹      总 12 · 已同步 7 · 未同步 5
              同步中 1 · 失败 2
会话归一化    待处理 3 · 已处理 8 · 已导入 4
归因分析      已分析 96 · 待分析 40
              问题 58 · 非问题 38
```

- "问题数量"对应 bad_cases 目录同步（本文），放最上面；"问题轨迹"对应 [11 章](11-bad-case-session-sync.md)。
- "归因分析"只读 `bad_case_analysis` 做整体统计，不在本特性实现归因逻辑；统计口径见 §6.4。
- 摘要胶囊是否增加徽标：保持现有"问题轨迹 7/12"不变，四段统计只进浮层，避免顶栏拥挤；`aria-label` 合并全部统计。
- `unavailable` 显示"未配置坏例查询服务"，不标红。
- 轮询复用 `acquisitionStatus` query；不新增 SSE、页面或手动触发按钮。
- 390px 宽度下浮层不溢出；沿用现有 token 与字号。
- 空表不做特殊处理（已确认）：`bad_cases` 为 0 时浮层照常出现，问题数量/问题轨迹/归因分析显示 0，顶栏徽标显示"问题轨迹 0/0"；只有 `unavailable` 会把对应段文案换成"未配置…"，不隐藏任何段、不新增空态分支。

### 8.3 原型修改点

`plans/14-15-ui-prototype/harness-evolution.html`：

1. 浮层重排为四段：问题数量、问题轨迹、会话归一化、归因分析；每段使用 `.tn-sync-row`，状态补充用 `.tn-sync-sub`。
2. "问题数量"行显示"总 <b>136</b> · 已同步 <b>128</b> · 未同步 <b>8</b>"，子行显示"空闲 · 游标 #128"。
3. 新增"归因分析"行："已分析 <b>96</b> · 待分析 <b>40</b>"，子行"问题 <b>58</b> · 非问题 <b>38</b>"。
4. 更新 `<summary>` 的 `aria-label`，包含四段统计。
5. 不改变浮层宽度、间距与移动端断点。

## 9. 配置

| 变量 | 默认 | 说明 |
|---|---|---|
| `HE_BAD_CASE_QUERY_BASE_URL` | 空 | 坏例查询服务地址；缺失即 `unavailable` |
| `HE_BAD_CASE_QUERY_TOKEN` | 空 | 服务令牌 |
| `HE_BAD_CASE_QUERY_TIMEOUT_SECONDS` | `30` | 单次请求超时 |
| `HE_BAD_CASE_QUERY_RETRY_ATTEMPTS` | `2` | 重试次数（0–5） |
| `HE_BAD_CASE_QUERY_RETRY_BACKOFF_SECONDS` | `0.25` | 重试退避基数 |
| `HE_BAD_CASE_CATALOG_SYNC_INTERVAL_SECONDS` | `300` | 定时间隔；`0` 关闭 |
| `HE_BAD_CASE_CATALOG_SYNC_PAGE_SIZE` | `200` | 页大小（1–200） |
| `HE_BAD_CASE_CATALOG_SYNC_TIME_BUDGET_SECONDS` | `300` | 单次运行时间预算 |
| `HE_BAD_CASE_CATALOG_SYNC_MAX_PAGES` | `100` | 单次运行最大页数 |

不复用 `HE_SESSION_QUERY_*`：两个服务的令牌与版本可能不同。mock 服务可以把两者指向同一地址。

## 10. 测试与验收

单元 / 集成：

- 客户端：正常页、空页、`total` 回显、id 非递增、字段缺失、非法时间、超限、401、429 重试、串行不重叠。
- 翻页：3 页后空页停止；`max_pages`/时间预算截断；游标单调递增。
- upsert：新 id 插入、已存在 id 更新、重复同步不增行、关联表不受影响；SQLite 与 MySQL 双库。
- 事务：页内失败整页回滚、游标不动；重试后数据完整。
- 冷启动：状态表为空时游标从 0 开始，已有行全部走 upsert 更新路径。
- 调度：启动立即触发一次；活跃 job 时跳过；失败后下个 tick 重试。
- 归因统计：三种 `analysis_status` 的组合计数；缺分析行计入 `pending`；孤儿归因行不计入。
- 统计 API 与前端浮层：四段顺序固定为问题数量、问题轨迹、会话归一化、归因分析；unavailable/idle/running/failed 四态；390px 不溢出。
- 契约：`contract:check` 绿。

独立验证命令：

```sh
pnpm test:api -- tests/m6-16-bad-case-catalog-sync
pnpm test:db
pnpm test:web
pnpm test:e2e -- "m6-16"
pnpm contract:check
pnpm verify:flow
pnpm lint:docs
```

冒烟：起一个 mock 服务，同时提供坏例分页接口与 m6-15 的两个会话查询接口（children / trajectory），让"目录同步 → bad_cases 入库 → 根会话轨迹补齐 → 会话可查"完整跑通，报告落在 `reports/`。

## 11. 已确认与待确认

已确认：

- 已存在的 `bad_case_id` 做更新，不新增行（用户 2026-10-30 明确）。
- 定时任务串行、不并发；启动时若上次已结束立即执行。
- 前端展示放在现有"数据同步"浮层，不新增页面。
- 冷启动从 0 开始，首轮全量重拉并 upsert 更新存量（2026-10-30 确认）。
- `limit` 就是 items 的条数上限；客户端只校验 `len(items) <= limit`，不依赖 `total - offset` 公式（同日确认）。
- "已同步数量"用 `COUNT(bad_cases)`；页大小默认 200（同日确认）。
- 时间戳缺失不判非法：`created_at` / `updated_at` 列是 NOT NULL，用本次同步时间兜底；存在时必须是带时区 ISO-8601（同日确认）。
- 浮层顺序固定为问题数量 → 问题轨迹 → 会话归一化 → 归因分析；归因分析只读 `bad_case_analysis` 展示整体进度，不在本特性实现归因（同日确认）。
- 空表（`bad_cases` 为 0）不做特殊处理：浮层照常出现并显示 0 值，徽标显示 `0/0`，不新增空态或隐藏逻辑（同日确认）。

| # | 问题 | 结论 |
|---|---|---|
| Q1 | 冷启动游标 | 从 0 全量重拉，upsert 更新存量 |
| Q2 | items 数量 | `limit` 是上限，校验 `len(items) <= limit` |
| Q3 | 已同步口径 | `COUNT(bad_cases)` |
| Q4 | 页大小 | 200 |
| Q5 | 时间戳缺失 | 不判非法；NOT NULL 用同步时间兜底 |


## 12. 文档更新与影响面

- [06 §1](../fullstack-design/06-database-design.md)：问题侧从"只读"改为"外部写 + 目录同步写，按主键幂等"；§4.1 增加写入路径与 upsert 说明，新增 §4.x 状态表。
- [05 §4.8](../fullstack-design/05-api-design.md)：`GET /api/acquisition/status` 增加 `badCaseSync`（补 m6-15 的文档漂移）、`badCaseCatalogSync` 与 `badCaseAnalysis`。
- `docs/architecture.md` 与 `.en.md`：外部问题表"只读"的表述收敛为"外部写 + 同步维护"。
- `plans/fullstack-design/README.md`：索引增加 12 章。
- 新增 Agent Note：记录"目录同步与外部直写并存"的决策与游标设计。

风险：

- 上游接口未提供真实 path/token：先用 mock 与配置适配层，真实值接入时不改业务层。
- 与外部直写并存：双方都按主键写，理论上以最后写入为准；本服务不删除行。
- 旧记录内容变更无法感知：接口只按 id 增量，这是契约限制，不作为缺陷。
