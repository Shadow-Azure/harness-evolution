# Agent Note: 空间 Session 最新 10 条投影、精确 root ID 查询与待同步计数

Status: implemented

[English](2026-11-16-workspace-session-latest-ten.en.md) | 中文

## Problem

m7 的 `GET /api/workspaces/{wid}/sessions` 已经按空间 bad case 投影根会话，但沿用了 legacy 列表的分页与检索语义：默认最多 100 条、`q` 是标题或 ID 的子串模糊匹配。空间 Session 页需要在打开时只拉最新 10 条，并让用户输入完整 root session ID 回车后精确落到那条会话——即使它已经不在最新 10 条里。页面同时要显示两个不同的总数：当前筛选下匹配多少条，以及这个空间里有多少根会话还没有归一化轨迹（待同步）。模糊匹配在这两件事上都不成立：短 UUID 片段可能命中多条，标题子串会把「按 ID 查询」变成无法预期的结果；而把 `bad_cases` 行数当作待同步数又会重复计算同一根会话，并随 `q`/`status` 变化。

## Decision

- V1 `GET /api/sessions` 冻结：保留 `search_text` + `id` 的子串搜索与 `limit=100` 默认值；V2 `GET /api/workspaces/{wid}/sessions` 的 `q` 改为完整 root session ID 精确匹配（`lower(id) = lower(trim(q))`），默认 `limit=10`。同一个 `SessionService.list` 通过 `SessionFilters.exact_query` 分流，两个端点共享 DTO 与装配逻辑，但检索语义不互相污染。
- 精确模式只在完整 ID 上生效：部分 UUID、标题片段、空 `q`（含全空白）都不会退化成模糊查询；非空但只有空白视为未提供查询，返回最新 10 条。
- 列表与计数共用 `_session_conditions` 生成同一组谓词：空间投影、`q`（精确或模糊）、`status` 只写一次。`count_sessions` 用同一组谓词、不带 `limit`，因此 `total` 是忽略分页后的匹配总数，不会因前端翻页或 `limit` 变化而漂移。
- `pendingSessions` 的口径是「当前空间内 `bad_cases.bad_case_session_id` 去重后没有对应 `session_families` 行的根数」，用 `NOT EXISTS` 子查询实现；它按空间 scope 计算，与 `q`、`status`、`sort`、`limit` 全部无关。待同步根只贡献计数，永不进入 `items`。
- 空间投影仍是 `session_families.id IN (SELECT bad_case_session_id FROM bad_cases WHERE workspace_id 命中 scope)`；精确 `q` 只在这个投影内收窄。别的空间上报的同一 ID 或只属于别的空间的根不会出现在结果里。
- 默认排序固定为 `started_at DESC, id ASC`：时间戳相同的会话也有确定性顺序，分页与断言不依赖数据库的隐式行序。
- 外部 `bad_cases` 表不存在时，列表、`total`、`pendingSessions` 统一退化为 `0`/空数组，沿用 `_scoped_reads_available` 的探测与缓存，不让新安装的 Session 页直接 500。
- `SessionListResponse` 增加 `total` 与 `pendingSessions` 两个必填字段；V1 也返回它们（additive），但 V1 的检索与默认 `limit` 不变。FastAPI OpenAPI、`packages/contracts/openapi.json` 与生成类型由 `pnpm contract:generate` 同步。

## Alternatives considered

- **V2 继续复用模糊搜索**：拒绝。需求是「输入 root Session ID 回车查询」；子串匹配会让短 ID 命中多条，也会让标题片段意外命中，空态与选中状态都无法稳定判定。
- **前端先取 100 条再切最新 10**：拒绝。`total` 与 `pendingSessions` 需要服务端权威口径，前端切片还会把全量卡片和每页 bad case 计数都拉下来，失去分页意义。
- **先查全部匹配再在 Python 里数 total**：拒绝。等于把 `limit` 取消，空间会话变多后随列表线性变慢；`COUNT(*)` 与列表共用谓词更直接。
- **用 `LEFT JOIN session_families … WHERE id IS NULL` 统计待同步**：拒绝。投影本身是「bad_cases 根 → families」的半连接，`NOT EXISTS` 语义更贴近「没有 families 行」，也不会把多行 join 带进分页查询。
- **`pendingSessions = bad_cases 行数 - 已归一化根数`**：拒绝。同一根会话可被多次上报，差值会把 case 数当成根数；必须按 `bad_case_session_id` 去重。
- **`pendingSessions` 跟随 `q`/`status` 过滤**：拒绝。待同步是空间级运维信号；搜索一条不存在的 ID 时它应保持不变，否则页面角标会在查询时消失。
- **新增待同步计数表或物化列**：拒绝。`session_families` 由重放写入、`bad_cases` 由外部上报写入，本服务没有跨表失效通知；计数是低频读，实时 `COUNT` 比缓存更诚实，也避免本 issue 引入迁移。
- **把 V1 默认 `limit` 也改成 10 或让 V1 用精确搜索**：拒绝。V1 已冻结，旧调用方依赖模糊搜索与 100 条默认值；新语义只落在 V2。

## Consequences

- 一次 V2 列表请求固定多出两条聚合查询（`count_sessions` 与 `count_pending_sessions`），加上原有的当前页 bad case 计数；三条查询都走空间索引，数据量由空间投影决定。
- `lower(id) = lower(q)` 让精确搜索无法直接使用 `session_families` 主键的最左前缀（SQLite 的 `=` 区分大小写，MySQL 默认排序规则虽不区分，但统一写成 `lower` 才能跨方言一致）；空间投影子查询仍先按 `bad_cases(workspace_id, bad_case_session_id)` 收窄，精确 ID 命中通常只有一行。
- `pendingSessions` 与 `items`/`total` 独立，搜索无结果时页面仍可能显示「N 个待同步」；这是有意的：角标表达的是空间状态，不是检索结果。
- V1 响应新增两个字段，属于 additive 契约变化；严格的旧客户端若校验封闭响应体会看到多余字段，但仓库内没有这种消费者。
- 全空白 `q` 的行为等同未查询，与「精确匹配空白 ID」不同；这个边界由服务层统一 `strip` 决定，测试固定了默认最新 10 的结果。
- 外部 `bad_cases` 表的探测结果在 repository 生命周期内缓存；表在运行中被删除或创建时，需要重启进程才会重新探测，这与既有读路径一致。
