# 11 · bad_cases 根会话轨迹定时同步

> 本文回答：bad_cases 涉及的根会话轨迹如何自动补齐、状态如何记录、前端如何展示，以及定时任务重叠时怎么处理。
> 前置：[04 后端架构](04-backend-architecture.md) · [05 接口设计](05-api-design.md) · [06 数据库设计](06-database-design.md) · [07 后端实现](07-backend-implementation.md) · [08 前端实现](08-frontend-implementation.md)。
> 状态：设计已确认（2026-10-30），待原型截图确认后实施。已确认项与遗留项见第 12 节。

## 1. 背景与目标

`bad_cases.bad_case_session_id` 指向问题所属的根会话，但本服务不保证该根会话的原始轨迹已经在 `trajectory_payloads` 中。现有轨迹入库只有两条路径：开发用本地导入，以及管理员手动 `POST /api/acquisition/pull`；两者都要求操作者知道 session id 或时间窗。bad_cases 持续增长时，问题详情、执行流图和自进化启动会因为缺少 payload 而看不到会话。

本特性新增一条自动补齐路径：定时扫描 bad_cases 的 distinct 根会话，筛出未同步的根会话，通过外部查询服务递归取得主 agent 与全部 subagent 的轨迹，写入 `trajectory_payloads`，再交给现有归一化/重放管线。状态表记录每个根会话的同步结果，前端展示总数、已同步与未同步。

目标：

- 不依赖人工触发，定时补齐 bad_cases 根会话的主/子 agent 轨迹。
- 同一根会话幂等；失败可重试；已同步不重复拉取。
- 外部轨迹查询接口严格串行，进程内不出现并发调用。
- 定时任务单飞；上一次未结束时下一次不得重复处理同一批根会话。
- 前端可看到根会话总数、已同步数、未同步数，以及同步中/失败状态。

非目标：

- 不改 bad_cases 的“外部写同库、本服务只读”边界。
- 不替换现有管理员手动 pull。
- 不在 CI 调用真实查询服务。
- 不做轨迹内容变更检测与全量重拉；是否增量重拉由本文第 12 节确认。

## 2. 数据流与组件

```text
bad_cases (external, read-only)
   │ distinct bad_case_session_id
   ▼
BadCaseRootSyncCoordinator (定时触发, 单飞)
   │ job kind = bad_case_root_sync
   ▼
BadCaseRootSyncService
   ├─ 选择未同步 root（状态表 + bad_cases）
   ├─ SessionQueryClient
   │    ├─ API 1: sessionId → 直接子 sessionId（逐层展开）
   │    └─ API 2: sessionId → 单 agent 轨迹（全局串行）
   ├─ write trajectory_payloads(source_type=http_api)
   ├─ replay_pending_payloads(...)  （复用现有管线）
   └─ update bad_case_root_sync
   ▼
GET /api/acquisition/status → badCaseSync 统计
   ▼
TopNav 数据同步浮层
```

组件归属：

| 组件 | 位置 | 职责 |
|---|---|---|
| `SessionQueryClient` | `apps/api/app/third_party_api/session_query/` | 两个外部接口的 HTTP 适配、严格响应模型、重试、串行锁 |
| `BadCaseRootSyncService` | `apps/api/app/service/acquisition/bad_case_sync.py` | 选择、遍历、payload 写入、状态更新、重放 |
| `BadCaseRootSyncCoordinator` | 同上或独立 `coordinator.py` | 定时循环、单飞触发、启动恢复 |
| `BadCaseRootSyncRepository` | `apps/api/app/db/crud/bad_case_sync.py` | 状态表读写、统计查询、claim/lease |
| 路由 | `apps/api/app/api/acquisition.py` | 扩展现有 status 响应；不新增写接口 |

## 3. 外部查询服务契约

两个接口都由服务端令牌鉴权，浏览器不直接调用。真实 path、token 形式与版本头暂未提供，先按可配置模板设计；维护者后续给出真实值后只改配置与适配层，不改业务层。

### 3.1 接口 1：直接子会话

```http
GET {base}/sessions/{sessionId}/children
Authorization: Bearer <service-token>
```

语义：传入主 agent 或 subagent 的 sessionId，返回它直接触发调用的 subagent sessionId；只返回一层，不递归。

响应是**裸数组**（客户端严格校验，元素必须是字符串，拒绝对象包装与未知字段）：

```json
["subagent-a", "subagent-b"]
```

空数组表示没有直接子会话，不是错误。若真实服务后续改成对象包装，只在适配层做一次显式映射，不把宽松解析带进业务层。

### 3.2 接口 2：单 agent 轨迹

```http
GET {base}/sessions/{sessionId}/trajectory
Authorization: Bearer <service-token>
Accept: application/x-ndjson
```

语义：返回该 agent 的完整轨迹，内容是纯轨迹数据，可以理解为直接对应 `trajectory_payloads.payload`；**不包含 `agent_meta`、`toolUseId`、`parentToolUseId` 等元数据**。浏览器直接访问会下载 `.jsonl`，Postman 中表现为多个 JSON object。

响应按 NDJSON 解析：每行一个 JSON object；空行跳过，但至少要有一个非空行。每个 object 用 `json.dumps(obj, ensure_ascii=False, separators=(",", ":"))` 重新序列化为一行，行间 `\n`；`content_hash = sha256(规范化后的 UTF-8 字节)`；`line_count = object 数`。空轨迹、非 object 元素、重复 JSON key、超长行都拒绝并记为稳定错误码。按 `\n` 分帧而不是 `splitlines`，避免合法 JSON 字符串里的 U+2028/U+2029 被误切。响应体上限 64 MiB、单行上限 1 MiB、行数上限 1,000,000；超限记 `SESSION_QUERY_INVALID_RESPONSE`。

接口 2 禁止并发：`SessionQueryClient` 内部用一把 `asyncio.Lock` 包住每次请求；同一进程内所有调用方共享这把锁。测试必须记录调用区间并断言不重叠。

### 3.3 超时、重试与错误

- 连接/读取超时、重试次数走环境变量；重试只针对超时、连接错误、429、5xx。
- 4xx 不重试；401/403 映射为 `SESSION_QUERY_UNAUTHORIZED`，不泄露响应正文。
- 响应不符合契约 → `SESSION_QUERY_INVALID_RESPONSE`；接口版本头（若提供）主版本不匹配 → `SESSION_QUERY_VERSION_INCOMPATIBLE`。
- 每个 agent 的失败只影响该 root；root 标记 `failed`，不中断整批。

## 4. 遍历与 payload 写入

### 4.1 遍历算法

从根会话开始广度优先：

```text
queue = [(root_session_id, parent=None, depth=0)]
visited = {root_session_id}
while queue:
    session_id, parent_id, depth = queue.popleft()
    if depth > max_depth: fail(root, TRAVERSAL_DEPTH_EXCEEDED)
    transcript = client.fetch_trajectory(session_id)   # 串行
    write_payload(session_id, parent_id, transcript)
    for child in client.list_children(session_id):     # 串行
        if child not in visited:
            visited.add(child)
            queue.append((child, session_id, depth + 1))
```

约束：

- `visited` 去重并防环；重复 child 只入队一次。
- `max_depth`、`max_agents` 可配置；超限把 root 标记失败并记录 `TRAVERSAL_LIMIT_EXCEEDED`，避免上游异常导致无限展开。
- API 1 失败时该 root 失败；已写入的 payload 保留，下次重试幂等覆盖。
- API 2 失败时该 agent 失败，root 失败；是否继续遍历其子节点由实现选择“失败即停”或“继续其他分支”，推荐失败即停，减少无效调用。
- 主 agent 的 `agent_id = root_session_id`，`agent_kind=main`，`agent_meta=NULL`；subagent 的 `agent_id = 查询用的 sessionId`，`agent_kind=subagent`。

### 4.2 `agent_meta` 与父子边

接口 2 只返回轨迹正文，没有 `agent_meta`，也没有触发子 agent 的 `tool_use_id`。本特性只能从接口 1 的父子 sessionId 关系构造边：

- 主 agent：`agent_meta = NULL`。
- subagent：`agent_meta = {"parentAgentId": parent_id}`；不写 `toolUseId`、`agentType` 等无法从接口获得的信息。

现有组树逻辑优先用 `agent_meta.toolUseId` 匹配父 agent 的 Agent 触发事件；本特性没有这个值，因此需要一条受控回退：

1. 若 `parent_tool_use_id` 存在，维持现有逻辑，锚到具体 Agent 触发事件。
2. 若没有 `parent_tool_use_id`，但有 `parentAgentId` 且对应父 agent 已存在：把子节点挂到父 agent 节点，锚到父节点最后一个事件，并记录 `PARENT_ANCHORED_BY_AGENT` 诊断（不作为失败）。
3. 若连 `parentAgentId` 也没有：维持现有降级，挂到主节点并记录 `MISSING_PARENT_TOOL_USE_ID`。

配套改动：

- `ParsedTranscript` 增加 `parent_agent_id`，`normalize_transcript` 从 `agent_meta.parentAgentId` 读取；`agents.parent_agent_id` 仍由组树写入。
- `agent_tree` 在普通 subagent 分支先尝试 `tool_use_id`，再尝试 `parent_agent_id`；`parent_agent_id` 的锚点取父节点最后一个事件，保证图上有确定的边。
- 修正现有 pull 路径的键名不一致：`normalize_transcript` 读取 `toolUseId` 时同时接受 `parentToolUseId`，优先 `toolUseId`；新写入统一使用 `parentAgentId`（本特性）或 `toolUseId`（有真实触发 id 时）。

这样即使接口 2 不提供元数据，subagent 仍能挂在正确的父 agent 下，只是无法精确到“父 agent 的哪一次 Agent 调用”；这是本特性可接受的展示精度。

### 4.3 payload 行

沿用 `trajectory_payloads` 现有结构，不新增列：

| 列 | 值 |
|---|---|
| `root_session_id` | bad_cases 的根 sessionId |
| `agent_id` | 主 agent = root；subagent = 接口 1 返回的 sessionId |
| `agent_kind` | `main` / `subagent` |
| `payload` | 规范化 JSONL |
| `agent_meta` | 主 agent NULL；subagent 为 `{"parentAgentId": parent_id}` |
| `content_hash` | 规范化 payload 的 sha256 |
| `line_count` | object 数 |
| `source_type` | `http_api` |
| `updated_at` | 本次写入时间（Asia/Shanghai） |

写入复用 `write_local_payloads(database, payloads, source_type="http_api")`；每个 agent 取到后立即以单行事务写入，失败时已写入的行保留，`agent_count` 记录实际行数，重试按 `(root_session_id, agent_id)` 幂等覆盖。写入完成后调用一次 `replay_pending_payloads(database, source_type="http_api", sync_run_id=job.id)`，与 `UpstreamPullService` 保持一致。状态表的 `synced` 只表示 payload 已完整写入；重放失败进入 `sync_runs.errors`，由现有 sync 调度重试，不回滚 root 状态。

## 5. 状态表与状态机

### 5.1 表 `bad_case_root_sync`

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `root_session_id` | `VARCHAR(36)` | PK | bad_cases 根会话 id |
| `status` | `VARCHAR(16)` | NOT NULL | `pending` / `syncing` / `synced` / `failed` |
| `attempts` | `INTEGER` | NOT NULL | 已尝试次数 |
| `last_error` | `TEXT` | NULL | 脱敏后的稳定 code + message |
| `agent_count` | `INTEGER` | NOT NULL | 该 root 在 `trajectory_payloads` 的实际行数（含 main）；失败时为已写入的部分值，成功时 ≥1 |
| `started_at` | `DATETIME` | NULL | 本次 claim 时间 |
| `synced_at` | `DATETIME` | NULL | 最近成功时间 |
| `next_retry_at` | `DATETIME` | NULL | 失败后的下次可重试时间 |
| `lease_owner` | `VARCHAR(128)` | NULL | 进程/任务标识 |
| `lease_expires_at` | `DATETIME` | NULL | claim 租约到期 |
| `updated_at` | `DATETIME` | NOT NULL | 最近状态变更 |

索引：`INDEX(status, next_retry_at)`；`root_session_id` 已是主键。

### 5.2 状态机

```text
(no row) --claim--> syncing --success--> synced
                       │
                       └--failure--> failed --retry_due/claim--> syncing
syncing --lease expired--> syncing (reclaim) / pending
```

- `synced` 是吸收态；同一根会话后续新增 bad_cases 不触发重拉。
- `failed` 不自动立刻重试；`next_retry_at` 到点后由下一轮扫描重新 claim。
- 租约过期只允许重新 claim，不删除已有 payload；重试幂等覆盖。
- 根会话从 bad_cases 消失时保留状态行，但统计忽略。
- `pending` 可以不落库：扫描时把“无状态行”视为 pending，claim 时再插入。

### 5.3 选择查询

```sql
SELECT DISTINCT bc.bad_case_session_id
FROM bad_cases bc
LEFT JOIN bad_case_root_sync s
  ON s.root_session_id = bc.bad_case_session_id
WHERE s.root_session_id IS NULL
   OR (s.status = 'failed' AND (s.next_retry_at IS NULL OR s.next_retry_at <= :now))
   OR (s.status = 'syncing' AND s.lease_expires_at <= :now)
ORDER BY bc.bad_case_session_id
LIMIT :batch_size
```

claim 在事务内先查后写，避免依赖方言 upsert：

1. `SELECT ... FOR UPDATE`（MySQL）或条件更新（SQLite）确认当前状态可 claim；
2. 写 `status=syncing`、`attempts += 1`、`started_at=now`、`lease_owner`、`lease_expires_at`；
3. 失败/成功分别写 `failed` / `synced`。

### 5.4 bad_cases 与状态表关联不上的两种情况

`bad_case_root_sync` 不是 `bad_cases` 的子表，也没有外键；两张表通过 `root_session_id` 做逻辑关联。关联不上分两种方向，语义不同：

| 情况 | 含义 | 处理 |
|---|---|---|
| `bad_cases` 有 root，状态表没有行 | 新发现、从未同步过的根会话 | 算入 `total` 与 `unsynced`；候选查询包含它；claim 时插入状态行 |
| 状态表有 root，`bad_cases` 已无该 root | 问题被删除/迁移后留下的审计行 | 不进 `total`/`synced`/`unsynced`；候选查询不选它；保留状态行用于审计，不主动删除 |

补充规则：

- 同一个 root 在 `bad_cases` 里出现多条记录时，`SELECT DISTINCT bad_case_session_id` 只算一次。
- 已 `synced` 的 root 后续新增 bad_cases 行，不触发重拉；状态仍是 `synced`，payload 复用。
- 已 `failed` 的 root 后续新增 bad_cases 行，不改变退避；到 `next_retry_at` 后照常重试。
- 状态表行在 root 消失后仍保留；如果之后同一 root 重新出现在 bad_cases，按原状态继续（`synced` 不重拉，`failed` 按退避重试）。
- 候选查询必须从 `bad_cases` 的 distinct root 出发做 `LEFT JOIN`，不能从状态表出发做 `INNER JOIN`，否则“关联不到状态表”的新 root 永远不会被处理。

## 6. 定时调度、并发与重入

### 6.1 现有事实

- `JobRunner` 在单进程内用全局 `asyncio.Lock` 串行执行所有 handler；两个 job 不会真正并发。
- `job_runs` 是持久化真值；进程重启时 `recover()` 把残留 `running` 标成 `interrupted`。
- `sync` 已有自己的 `sync_lock` 单飞；`sync_lock` 目前只服务 `sync`。
- 现有调度器每 60s 触发一次 `sync`，只重放 payload，不访问上游。

### 6.2 已确认策略：跳过 + 状态驱动续跑

当定时器触发时：

1. 如果已有活跃的 `bad_case_root_sync` job（`job_runs` 中 `kind` 匹配且状态 `queued/running`），**直接跳过**本次 tick，记录日志/计数。
2. 否则查询未同步 root 数；为 0 也不提交 job。
3. 提交一个 `bad_case_root_sync` job，`ref_id` 使用固定值（如 `bad_case_root_sync`），payload 只带批次参数；`JobRunner.submit` 的重复检查作为第二道闸。
4. 单个 job 处理有限批量（`batch_size` 或 `time_budget`，先到先停）；结束时把剩余 root 留给下一 tick。
5. 下一次 tick 在 job 结束后重新按状态表扫描，不会重复已 `synced` 的 root。

为什么不是“排队一个后续 job”：

- 定时器本身就是后续机制；再排队会制造重复扫描和重复 job。
- `JobRunner` 已串行，排队只会延长其他 kind 的等待。
- 状态表是幂等真值，任何时刻重新扫描都能续跑，不需要队列保序。

为什么不是“取消上一个”：

- 已写入的 payload 是有效进度，取消会浪费串行接口调用。
- 取消需要额外的协作式取消与状态回滚，收益低。

### 6.3 重叠场景逐条

| 场景 | 行为 |
|---|---|
| 上一个 job 仍在 `running`，下一次 tick 到了 | 跳过，不提交新 job；日志记 `skipped_active` |
| 上一个 job 在 `queued` 但尚未执行 | 同样视为活跃，跳过 |
| 上一个 job 已结束但只处理了部分 root | 下一次 tick 重新扫描未同步 root，继续处理 |
| 上一个 job 失败退出 | 已 claim 的 root 标 `failed`，其余保持 `pending`；下一 tick 按退避重试 |
| 进程在 job 中途崩溃 | 重启后 `job_runs` 标 `interrupted`；`syncing` 行租约到期后重新 claim，未写入的 root 从 `pending` 继续 |
| 两个实例同时触发 | V1 不支持多实例；见 §6.4 |
| 手动 pull 与自动补齐同时运行 | `JobRunner` 串行执行；接口 2 锁只在新客户端内，手动 pull 使用的是另一套 trajectory 契约，不共享接口 2 |

### 6.4 多实例与跨进程

V1 与现有 `sync` 一样按单实例部署：`JobRunner` 的全局锁是进程内的，`sync_lock` 只保护 `sync`。如果未来多实例：

- 为 `bad_case_root_sync` 增加跨进程锁（复用 `sync_lock` 的 `name` 维度，新增 `name='bad_case_root_sync'` 的行，或引入通用 `job_locks` 表）。
- 状态表的 claim/lease 已经能防止两个实例处理同一 root，但接口 2 的“禁止并发”仍需跨进程信号量/数据库锁，不能只靠 `asyncio.Lock`。
- 多实例不在本 issue 的交付范围，但设计上不阻碍后续加锁。

## 7. API 与前端

### 7.1 扩展 `GET /api/acquisition/status`

在现有响应上增加一个嵌套对象，避免新增轮询端点：

```json
{
  "activeJobId": "job-1",
  "status": "running",
  "pending": 3,
  "processed": 8,
  "badCaseSync": {
    "total": 12,
    "synced": 7,
    "unsynced": 5,
    "syncing": 1,
    "failed": 2,
    "status": "running",
    "lastRunAt": "2026-10-30T12:00:00+08:00",
    "lastError": "SESSION_QUERY_TIMEOUT"
  }
}
```

- `total`：`COUNT(DISTINCT bad_cases.bad_case_session_id)`，查询时实时计算；没有状态行的新 root 也计入。
- `synced`：当前 bad_cases 根会话中状态为 `synced` 的数量；没有状态行的 root 不算已同步。
- `unsynced = total - synced`，包含 `syncing`、`failed` 与“还没有状态行”的 root。
- `syncing` / `failed`：当前 bad_cases 根会话中对应状态的数量，是 `unsynced` 的子集。
- 状态表有行但 bad_cases 已无该 root 时，该行不计入上述任何当前统计。
- `status`：`unavailable`（未配置查询服务）/ `idle` / `queued` / `running` / `failed`。
- `lastError` 只返回稳定 code，不返回上游正文。

### 7.2 前端展示

位置：沿用顶栏已有的“数据同步”浮层，在现有归一化统计下方增加一段“问题轨迹”：

```text
问题轨迹   总 12 · 已同步 7 · 未同步 5
           同步中 1 · 失败 2
```

- `unavailable` 显示“未配置轨迹查询服务”，不显示红色错误。
- `running` 显示“补齐中…”，数字沿用最近一次查询。
- `failed` 显示稳定错误文案，不暴露上游响应。
- 轮询复用 `acquisitionStatus` query；不新增 SSE、不新增页面路由。
- 成员可见统计；不新增手动触发按钮（自动任务，手动补拉仍走现有 admin pull，不在本页暴露）。

原型改动：在 `harness-evolution.html` 顶栏用户浮层/同步浮层中增加“问题轨迹”行与分隔线，保持现有字号、颜色 token 与 390px 布局；第 5 步提交修改前后截图。

## 8. 配置、迁移与可观测性

新增环境变量（均有默认值，`0` 关闭）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `HE_BAD_CASE_SYNC_INTERVAL_SECONDS` | `300` | 定时扫描间隔；`0` 关闭 |
| `HE_BAD_CASE_SYNC_BATCH_SIZE` | `20` | 单 job 最多处理 root 数 |
| `HE_BAD_CASE_SYNC_TIME_BUDGET_SECONDS` | `600` | 单 job 时间预算 |
| `HE_BAD_CASE_SYNC_MAX_AGENTS` | `200` | 单 root 最多 agent 数 |
| `HE_BAD_CASE_SYNC_MAX_DEPTH` | `10` | 单 root 最大展开深度 |
| `HE_BAD_CASE_SYNC_LEASE_SECONDS` | `900` | claim 租约 |
| `HE_SESSION_QUERY_BASE_URL` | 空 | 查询服务地址；缺失即 `unavailable` |
| `HE_SESSION_QUERY_TOKEN` | 空 | 服务令牌 |
| `HE_SESSION_QUERY_TIMEOUT_SECONDS` | `60` | 单次请求超时 |
| `HE_SESSION_QUERY_RETRY_ATTEMPTS` | `2` | 重试次数 |

迁移：新增 `0011_bad_case_root_sync.py`，只建服务自有表，不碰外部表。启动迁移仍传 `bootstrap_external_tables=False`。

可观测性：

- `job_runs.result` 记录 `rootsConsidered`、`rootsSynced`、`rootsFailed`、`agentsFetched`、`payloadsInserted`、`payloadsUpdated`、`replayed`、`skippedTicks`。
- `bad_case_root_sync.last_error` 记录稳定 code；日志只记 sessionId 前缀/数量，不记轨迹正文。
- 新增错误码：`SESSION_QUERY_UNAVAILABLE`、`SESSION_QUERY_UNAUTHORIZED`、`SESSION_QUERY_VERSION_INCOMPATIBLE`、`SESSION_QUERY_INVALID_RESPONSE`、`SESSION_QUERY_TIMEOUT`、`TRAVERSAL_LIMIT_EXCEEDED`、`TRAJECTORY_EMPTY`、`BAD_CASE_SYNC_TIME_BUDGET`。

## 9. 失败、重试与数据一致性

- 单 root 失败隔离：一个 root 的接口失败不影响同批其他 root。
- 单 root 也受批次时间预算约束：每取一个 agent 前检查 deadline，超限记 `BAD_CASE_SYNC_TIME_BUDGET`，已写入的 payload 保留，root 进入退避重试。
- 重试退避：`attempts=1→1m`、`2→5m`、`3→15m`、`>=4→1h`，写入 `next_retry_at`；可配置。
- 已写入 payload 不回滚；重试按 `(root_session_id, agent_id)` 幂等覆盖；失败时 `agent_count` 记录已写入行数。
- 租约按每个 root 的实际 claim 时间计算，并在每个 agent 写入后续期；租约长度至少覆盖单 root 的时间预算。
- `synced` 与 payload 完整性：状态在遍历完成且所有 payload 写入成功后置 `synced`；`agent_count` 为实际写入行数。
- 状态与 payload 漂移：若人工删除 payload，状态仍为 `synced`，统计不会自动发现；本 issue 不做自动对账，可在后续加健康检查。
- 已有 payload 的根会话：见 §9.1。

### 9.1 冷启动：状态表为空但 payload 已存在

上线时 `bad_case_root_sync` 是空表，而 `trajectory_payloads` 可能已经有历史数据（本地导入、管理员 pull、旧脚本写入）。扫描只看状态表，因此这些 root 会被当成“未同步”，第一次跑就会重新走一遍接口 1/2。

可选处理：

| 方案 | 做法 | 结果 |
|---|---|---|
| A. 接受一次重拉（推荐） | 不特殊处理，按批量/时间预算逐步补齐 | 状态与 subagent 完整性都由真实遍历保证；代价是首轮 API 2 调用量等于历史 root 数 |
| B. 按主 payload 直接标记 synced | 看到 `trajectory_payloads` 有 main 行就写 `synced` | 不重拉，但无法知道 subagent 是否齐全；状态可能长期说谎 |
| C. 只用接口 1 校验 | 对已有 root 调接口 1 展开，比较 payload 行；缺失的才调接口 2 | 比 B 准确、比 A 省接口 2；但实现更复杂，且仍要遍历全部历史 root |

推荐 A：状态表的价值是“可验证的完整”，不是“尽量少调用”。批量与时间预算已经把首轮压力摊到多个 tick；如果历史数据量导致首轮过慢，再单独做一次性 bootstrap 脚本（C），不作为自动路径的默认行为。

补充：`agent_count` 只用于诊断/详情，不参与前端总数/已同步/未同步统计；统计只看 `status='synced'`，避免“有 main 行就算同步”的误判。

## 10. 测试与验收

单元/集成：

- 遍历：多层、重复 child、环、深度/数量超限。
- 串行：记录 API 2 调用开始/结束，断言无重叠。
- 状态机：claim、成功、失败退避、租约回收、幂等重跑。
- 选择查询：只选未同步/到期失败/过期 syncing，不选 synced。
- 调度重叠：active job 存在时 tick 跳过；job 结束后下一次继续。
- 崩溃恢复：`running` job + `syncing` 行 → 重启后重新 claim。
- 响应解析：NDJSON 正常、空体、非 object、重复 key、超长行；空数组（接口 1）不是错误。
- 统计 API：总数/已同步/未同步与状态表一致。
- 前端：浮层加载/空/失败/运行态；390px 不溢出。
- 契约：`AcquisitionStatusResponse` 新增字段后 `contract:check` 绿。

独立验证命令：

```sh
pnpm test:api -- tests/m6-15-bad-case-session-sync
pnpm test:db
pnpm test:web
pnpm test:e2e -- "m6 bad case sync"
pnpm contract:check
pnpm verify:flow
pnpm lint:docs
```

## 11. 交付顺序

1. 设计确认完成，补 05/06/07/08 的对应小节。
2. 契约：`AcquisitionStatusResponse.badCaseSync` + 生成类型；状态表迁移。
3. 客户端与遍历：mock 契约测试先行，再接服务。
4. 调度与单飞：复用 `JobRunner`，启动/停止接入 lifespan。
5. 前端：顶栏浮层 + 组件测试。
6. 冒烟：本地 mock 查询服务，验证两个接口、串行、重叠与统计。

## 12. 已确认决策与遗留项

已确认（2026-10-30）：

| # | 问题 | 结论 |
|---|---|---|
| 1 | 接口路径与鉴权 | 先用可配置模板与 mock 契约；真实值由维护者后续给出，只改配置与适配层 |
| 2 | 接口 1 响应 | 裸数组，元素为 subagent sessionId |
| 3 | 接口 2 响应 | NDJSON 纯轨迹，无 `agent_meta`；父子边用 `parentAgentId` 回退 |
| 4 | 重叠策略 | 跳过 + 状态驱动续跑，不排队、不取消 |
| 5 | `synced` 语义 | payload 完整即 `synced`，重放由现有 sync 负责，不回滚状态 |
| 6 | 冷启动 | 默认 A：接受首轮重拉，按批量/时间预算摊开；如需优化另做 bootstrap |
| 7 | 批量/间隔默认值 | 300s / 20 roots / 600s / 200 agents / depth 10 |
| 8 | 前端位置 | 顶栏“数据同步”浮层，不新增页面路由 |

仍需维护者后续提供/调整：

- 两个接口的真实 path、token 形式、版本头与响应样例；当前 mock 使用 `/sessions/{sessionId}/children` 与 `/sessions/{sessionId}/trajectory`。
- 冷启动若选择 C（接口 1 校验 + 缺失才拉），实现前告知；默认按 A。
- `agent_count` 字段名是否改为 `payload_count` 可在实现前调整；当前设计保留 `agent_count`，语义明确为该 root 在 `trajectory_payloads` 的实际行数（含 main）。
