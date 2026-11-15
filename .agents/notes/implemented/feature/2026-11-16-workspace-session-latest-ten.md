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
- `total` 与 `pendingSessions` 不是同一集合的划分：`total` 只数当前 `q`/`status` 下已归一化的根、**不含 pending**；`pendingSessions` 与 `q`/`status` 无关；两者不能相加成「空间全部被上报的根」，需要该语义时应新增字段而不是改 `total`。
- 共享 root 的计数口径：同一 root 被两个空间上报时，V2 的 `total`/`pendingSessions` 在每个空间各算一次（每个空间都要补自己的轨迹）；V1 的可见空间并集用 `IN` 半连接按根去重，同一根只算一次。V1 也计算这两个计数（additive），但它的 `pendingSessions` 是可见空间并集去重口径，与 V2 的单空间角标同名不同集合。
- 空间投影仍是 `session_families.id IN (SELECT bad_case_session_id FROM bad_cases WHERE workspace_id 命中 scope)`；精确 `q` 只在这个投影内收窄。别的空间上报的同一 ID 或只属于别的空间的根不会出现在结果里。
- 默认排序固定为 `started_at DESC, id ASC`：时间戳相同的会话也有确定性顺序，分页与断言不依赖数据库的隐式行序。
- 外部 `bad_cases` 表不存在时，列表、`total`、`pendingSessions` 统一退化为 `0`/空数组，沿用 `_scoped_reads_available` 的探测与缓存，不让新安装的 Session 页直接 500。
- `SessionListResponse` 增加 `total` 与 `pendingSessions` 两个必填字段；V1 也返回它们（additive），但 V1 的检索与默认 `limit` 不变。FastAPI OpenAPI、`packages/contracts/openapi.json` 与生成类型由 `pnpm contract:generate` 同步；V2 的 `q` 与两个计数在 OpenAPI 中都带 `description`，说明精确语义与口径。
- 过渡期：本 PR 只落地 V2 的 `q` 与计数，现有 Session 页仍用 300ms 防抖并把输入原样当 `q` 发送。搜索框文案因此只承诺「完整 root Session ID」，标题/仓库检索在 m8-05 加入回车与「最新 10 / 总数」交互前不开放。

## Alternatives considered

- **V2 继续复用模糊搜索**：拒绝。需求是「输入 root Session ID 回车查询」；子串匹配会让短 ID 命中多条，也会让标题片段意外命中，空态与选中状态都无法稳定判定。
- **前端先取 100 条再切最新 10**：拒绝。`total` 与 `pendingSessions` 需要服务端权威口径，前端切片还会把全量卡片和每页 bad case 计数都拉下来，失去分页意义。
- **先查全部匹配再在 Python 里数 total**：拒绝。等于把 `limit` 取消，空间会话变多后随列表线性变慢；`COUNT(*)` 与列表共用谓词更直接。
- **用 `LEFT JOIN session_families … WHERE id IS NULL` 统计待同步**：拒绝。投影本身是「bad_cases 根 → families」的半连接，`NOT EXISTS` 语义更贴近「没有 families 行」，也不会把多行 join 带进分页查询。
- **`pendingSessions = bad_cases 行数 - 已归一化根数`**：拒绝。同一根会话可被多次上报，差值会把 case 数当成根数；必须按 `bad_case_session_id` 去重。
- **`pendingSessions` 跟随 `q`/`status` 过滤**：拒绝。待同步是空间级运维信号；搜索一条不存在的 ID 时它应保持不变，否则页面角标会在查询时消失。
- **新增待同步计数表或物化列**：拒绝。`session_families` 由重放写入、`bad_cases` 由外部上报写入，本服务没有跨表失效通知；计数是低频读，实时 `COUNT` 比缓存更诚实，也避免本 issue 引入迁移。
- **把 V1 默认 `limit` 也改成 10 或让 V1 用精确搜索**：拒绝。V1 已冻结，旧调用方依赖模糊搜索与 100 条默认值；新语义只落在 V2。
- **在过渡期保留「标题/仓库」搜索文案**：拒绝。V2 `q` 已不再匹配 `search_text`，继续承诺会让用户看到永远为空的检索；最小文案/空态修正比同 PR 改交互风险低，完整回车交互留给 m8-05。

## Consequences

- 一次 V2 列表请求固定多出两条聚合查询（`count_sessions` 与 `count_pending_sessions`），加上原有的当前页 bad case 计数；三条查询都走空间索引，数据量由空间投影决定。
- SQLite 实测计划（2026-11-16）：精确列表为 `SEARCH session_families USING COVERING INDEX sqlite_autoindex_session_families_1 (id=?)` + `LIST SUBQUERY` + 临时 B-tree 排序；pending 为 `SEARCH bad_cases USING COVERING INDEX ix_bad_cases_workspace_session (workspace_id=?)` + `SEARCH session_families USING COVERING INDEX sqlite_autoindex_session_families_1 (id=?)`。所以 `lower(id)` 并不妨碍 SQLite 用上主键；它只是让「一定走索引」无法跨方言保证，MySQL 的执行计划仍未在本地验证（本地无 MySQL 服务，由 CI mysql lane 承接）。
- 列表响应不是单一快照：`items`、当前页 case 计数、`total`、`pendingSessions` 各开一个读会话。tree 路径已有 `tree_snapshot` 单会话先例；这里没有照做。重放会删除并重建 `session_families`，若恰好落在两次查询之间，可能出现 `total < len(items)` 或 pending 与页内数据短暂不一致；窗口毫秒级、读多写少，本 PR 接受并记录，不引入新的快照机制。
- `pendingSessions` 与 `items`/`total` 独立，搜索无结果时页面仍可能显示「N 个待同步」；这是有意的：角标表达的是空间状态，不是检索结果。
- V1 响应新增两个字段，属于 additive 契约变化；严格的旧客户端若校验封闭响应体会看到多余字段，但仓库内没有这种消费者。V1 的 `pendingSessions` 按可见空间并集去重，与 V2 的单空间计数不是同一个集合。
- 共享 root 在两个空间各算一次是刻意的：A、B 各自都需要补轨迹，任一空间的角标都不应因另一空间已归一化而消失；V1 则是「当前用户能看到的空间」这一集合上的按根去重。
- 全空白 `q` 的行为等同未查询，与「精确匹配空白 ID」不同；这个边界由服务层唯一一次 `strip` 决定，请求边界与 repository 只消费已归一化的值，测试固定了默认最新 10 的结果。
- 过渡期（m8-05 前）现有页面的标题/仓库搜索会返回空结果，这是有意的 API-first 过渡；搜索框与空态已改为只承诺完整 root Session ID，并提示清空搜索可恢复列表。
- 外部 `bad_cases` 表的探测结果在 repository 生命周期内缓存；表在运行中被删除或创建时，需要重启进程才会重新探测，这与既有读路径一致。
