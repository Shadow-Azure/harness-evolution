# Agent Note: 工作空间 bad case 总览聚合 API

Status: implemented

[English](2026-11-16-workspace-overview-api.en.md) | 中文

## Problem

m8-01 让空间凭据可以把 bad case 上报进 `bad_cases`，m8-02 让空间 Session 列表能按空间投影取数，但空间总览页需要的不是单条会话或单条问题，而是「这个空间在某段时间里出了多少 bad case、来自哪些对象、沿时间怎么分布、按条件筛出来的分页列表」。这些数字必须在一个请求里给出可比口径：同一段时间内指标条、趋势、来源分布和列表的分子分母要能对上，否则页面上「6 个 bad case、趋势 5 个柱、列表 7 行」这种自相矛盾无法排查。同时它们必须只统计路径上的那个空间——bad case 由外部上报写入，跨空间串数据是安全事故而不是显示 bug。

## Decision

- 新增四个只读端点，全部挂 `require_workspace_role(wid, "viewer")`，全部把 `workspace_id` 固定为路径里的空间：`GET /api/workspaces/{wid}/overview/summary`、`/overview/trend`、`/overview/sources`、`GET /api/workspaces/{wid}/bad-cases`。空间不可见或不存在一律沿用 `404 WORKSPACE_NOT_FOUND`（防枚举），与 m7/m8 的读路径一致。
- 时间窗是**闭区间本地日期**：`from`/`to` 都给就原样使用，此时残留的 `range` 被忽略且**不校验**（`from/to/range=0` 合法）；都不给就用 `range`（默认 90，只接受 7/30/90）得到 `[今天-range+1, 今天]`；只给一个边界时必须显式带 `range`，该边界为锚点、按 `range` 补出另一侧（`from=X&range=7` → `[X, X+6]`，`to=Y&range=7` → `[Y-6, Y]`）。这样「窗口长度 = range」在任何入口都成立，不会出现「给了 from 又给了 range 却按今天收尾」的二义。`from > to`、单边界缺 `range`、跨度 >366 天、需要用 `range` 推导窗口而它不在 7/30/90 内、边界落在 `1970-01-01..2999-12-31` 之外（含 `date ± timedelta` 溢出）都返回 `422 WINDOW_INVALID`，不会落到 500。
- `grain` 在路由签名里声明为 `Literal["day","week","month"]`，OpenAPI 因此暴露允许值、生成的 TS 客户端得到联合类型；FastAPI 会在 handler 前校验，路由包装器把 `grain` 的 `RequestValidationError` 映射回专用 `422 GRAIN_INVALID`，所以非法值不落通用 `VALIDATION_INVALID`。`range` 因要在显式双边界时允许被忽略的任意残留值，保持 `int|None` 校验，只用 `json_schema_extra` 在 OpenAPI 里声明 `7/30/90`。
- 窗口边界与分桶都以 Asia/Shanghai 为准：SQL 用 `created_at >= start 00:00+08` 与 `created_at < (end+1) 00:00+08` 半开区间表达闭区间日期，`+08:00` 的 `00:30` 属于当天而不是前一天 UTC。日桶就是本地日；周桶按 ISO 周一起始，允许首桶早于窗口起点；月桶取当月 1 日。趋势只返回与窗口相交的桶，并且**补零**——没有 bad case 的那天/那周/那月仍然出现在 `buckets` 里，计数为 0。
- `grain=day` 在闭区间跨度 >92 天时降级为 `week`（93 天即降级，92 天保持日粒度），响应新增 `grain` 字段如实报告**本次实际生效**的粒度，前端不需要自己重算降级规则。`week`/`month` 不降级。
- 趋势分桶在 Python 里做：SQL 只按窗口取出 `(created_at, bad_case_type)`（窗口上限 366 天，行数受空间额度约束），再用 `window.py` 的纯函数落到桶里。这样「周一起始」「月首日」「补零」只有一份实现，且可以脱离数据库做单元测试；把 `strftime`/`date_trunc` 写进 SQL 会把同一套规则按方言复制两遍。
- `summary` 的口径：`badCases` = 窗口内行数，`self`/`discovery` = 窗口内两类行数，`sessions` = 窗口内 `COUNT(DISTINCT bad_case_session_id)`，`sources` = 窗口内 `COUNT(DISTINCT object_name)`。两条 distinct 与两类计数在同一条聚合 SQL 里出，避免同一组谓词被复制成四条查询。
- 所有总览读路径共用一条 `bad_case_type IN ('self','discovery')` 谓词：legacy 目录同步可能写入越界类型（写入侧只限列长），这些行不计入 `badCases/self/discovery/sessions/sources/objects` 与趋势，但仍计入空间级 `used`。这样 `badCases = self + discovery`、趋势总和与列表 `total` 始终一致，列表也不会因为一条 malformed 行而 500。
- `sessions` 数的是**窗口内被上报的根**，包含还没有归一化轨迹的 pending 根：总览回答的是「这段时间有多少根会话出过问题」，不是「有多少根已经能点开」。它不是 06 §7.5 的空间 Session 集合（JOIN `session_families`），也不等于 Session 页的 `total`，且不能与 `pendingSessions` 相加；这三处口径分别写进 06 §7.5、05 §3.10/§4.18 与 OpenAPI 字段描述。
- `quota`/`used` 是空间级、**不带窗口也不带对象/类型筛选**：`quota` 取 `workspaces.quota`，`used` 取该空间 `COUNT(bad_cases)`。额度语义是「凭据上报的准入上限」，所以总览必须显示真实占用（可能因为 legacy 目录同步超过 `quota`），而不是窗口内的条数；越界类型的行也只在这里计数。
- `objects` 选项列表来自窗口内 distinct `object_name`，**忽略 `objects` 筛选**（否则多选后其它选项会消失、无法再选回来），按 `lower(object_name)` 升序返回，大小写不敏感的字母序在示例里就是 `deep-research / Explore / workflow`。
- `sources` 一行一个对象：`total`、`self`、`discovery`、`sessions`（该对象的 distinct 根），排序 `total DESC, object ASC`，并列时对象名兜底，翻页与断言不依赖数据库隐式行序。
- 列表参数：`from/to`/`range`、`objects`、`badCaseType`（`all|self|discovery`，默认 `all`）、`page`（≥1，默认 1）、`pageSize`（1..50，默认 8）。`objects` 同时接受重复参数与逗号分隔值：两侧都按逗号切开、trim、丢空、按首次出现去重，空选择不加任何对象谓词；去重后 >50 项才是 `422 OBJECT_FILTER_TOO_LARGE`（所以 `?objects=a&objects=a,a` 合法）。
- 列表排序固定 `created_at DESC, bad_case_id ASC`：同一毫秒的多条上报也有确定顺序。`total` 与当前页共用同一组谓词，`page`/`pageSize` 只影响 `items`。
- `attributionCount` 是**去重 `(probe_type, probe_object, object_version)` 三元组**数，经 `bad_case_analysis JOIN probe_reports` 得到，只对当前页的 case id 算一次。今天 `bad_case_analysis` 对 `bad_case_id` 唯一，因此实际取值只有 0/1，但查询写成「先 distinct 三元组再 group by case」的形状，m10 改成一 case 多归因时不需要改代码。SQLite 不支持 `COUNT(DISTINCT a, b, c)`，MySQL 方言又不该泄漏到 repository，所以用 distinct 子查询 + 外层 `COUNT(*)`，两种方言同一条语句。
- `badCaseTypeLabel` 由服务端给（`self → 自身存在问题`、`discovery → 发现前置步骤问题`），与 05 §3.10 的 DTO 一致；列表不因为渲染语言不同而在前端重算标签。
- `triggerAt` 暂时等于 `createdAt`：m9-04 才引入对象触发点坐标，本 issue 不发明 schema，也不额外 join `agents`/`agent_events` 去猜触发时间。字段先按契约存在，05 §3.10 的示例、OpenAPI 描述与 Agent Note 都写明这段临时等价，避免前端把它当成真实触发时刻。
- 外部表探测按 repository 实例缓存：**首次探测时**缺失才降级——`bad_cases` 不存在时 summary 全零（`quota` 仍取空间行）、`objects` 为空、趋势只剩补零桶、sources 与列表为空；`bad_case_analysis` 或 `probe_reports` 不存在时列表照常返回，只是 `attributionCount` 全为 0。缓存是进程级的，运行中建表或删表不会重新探测：可能长期返回零/空，或在下一次查询抛数据库错误直到重启进程；这与 m8-02 的 `_scoped_reads_available` 同构，不能声称「任何时刻都没有 500」。
- `main.py` 只新增 composition root 的一行装配与路由注册，`errors.py` 只新增 `WINDOW_INVALID`、`GRAIN_INVALID`、`OBJECT_FILTER_TOO_LARGE` 三个码；契约由 `pnpm contract:generate` 生成 `packages/contracts/openapi.json` 与 `api.d.ts`，`test_openapi.py` 固定参数名、默认值、枚举与错误码。
- 05 §3.10/§4.18 与 06 §7.5 同步了窗口与列表参数（含 `range` 在显式双边界下被忽略、默认 90、`pageSize` 1..50）、桶 label 格式、`sessions` 的上报根口径、`triggerAt` 临时等价、`attributionCount` 的唯一定义以及越界 `bad_case_type` 的排除。

## Alternatives considered

- **用 `FILTER (WHERE …)` 写条件计数**：拒绝。SQLite 3.30+ 支持、MySQL 不支持，会把方言差异带进 repository；`SUM(CASE WHEN … THEN 1 ELSE 0 END)` 两边都能跑。
- **summary 拆成四条 `COUNT` 查询**：拒绝。四条查询各写一遍窗口/对象谓词，任何一处漏改都会让指标条内部分母不一致；一条聚合行同时给出两类计数与两个 distinct。
- **趋势用 SQL 生成桶序列（递归 CTE / `date_trunc`）**：拒绝。周一起始、月首日、降级阈值和补零在两种方言里写法不同，且 SQLite 的日期函数与 MySQL 的 `DATE_FORMAT` 行为不完全一致；把桶规则放在 Python 纯函数里只有一份实现，还能单测 92/93 天、闰日、跨年。
- **让 `sessions` 只数已归一化的根（JOIN `session_families`）**：拒绝。总览回答「这段时间有多少根被上报的会话出过问题」，pending 根同样是空间的事故输入；用 join 过滤会让「上报了 6 条、只显示 4 个会话」看起来像丢数据。待同步在 Session 页有独立指标。
- **`quota`/`used` 跟随时间窗**：拒绝。额度是空间准入状态，跟着窗口变会让「额度 60、已用 3」随筛选跳动，也无法解释上报为什么被 409 拒绝。
- **`objects` 选项跟随 `objects` 筛选**：拒绝。多选后未选中的对象会从下拉里消失，用户无法再选回来；选项是「这个窗口里有哪些对象」，与当前选择无关。
- **`sources` 并列时按对象名倒序或按数据库行序**：拒绝。分页/断言会随执行计划漂移；固定 `total DESC, object ASC` 才可复现。
- **`objects` 只接受重复参数**：拒绝。前端 URL 与 curl 调试都更常写 `?objects=a,b`，两种形式都收、统一 trim + 去重，成本只有一次 split。
- **超过 50 项时截断**：拒绝。静默截断会返回用户没选的数据子集，看起来像筛选失效；`422 OBJECT_FILTER_TOO_LARGE` 让调用方明确知道要收窄。
- **`COUNT(DISTINCT probe_type, probe_object, object_version)` 直接写进 SQL**：拒绝。MySQL 支持、SQLite 不支持；distinct 子查询在两边同义，且 m10 扩成一 case 多归因时不用改。
- **`triggerAt` 先返回 `null` 或先 join 触发点**：拒绝。`null` 会强迫前端为「已知字段」写空分支；join `agents`/`agent_events` 猜触发时刻属于 m9-04 的坐标语义，本 issue 不发明口径。返回 `created_at` 并显式声明是临时等价，比一个假装精确的猜测更诚实。
- **把 `objects` 上限写成 `pageSize` 那样的 FastAPI 约束**：拒绝。数量要在去重后算（重复参数不应触发上限），只能用自定义校验，因此错误码也必须是文档里的专用码而不是通用 `VALIDATION_INVALID`。
- **复用 problems 模块的 `BadCaseListResponse`**：拒绝。V1/V2 会话内问题列表是 `{items:[BadCase]}` 无分页，总览列表是 `{items,total,page,pageSize}`；同名会让 OpenAPI 出现 `app__service__overview__schemas__BadCaseListResponse` 这种模块限定名。改用 `OverviewBadCaseListResponse`，`BadCaseListItem` 保持 05 §3.10 的命名。

## Consequences

- 一次总览首屏固定发出四个请求：summary（1 条聚合 + 1 条额度查询 + 1 条对象选项）、trend（1 条窗口行查询 + Python 分桶）、sources（1 条分组聚合）、list（1 条 count + 1 条分页 + 0/1 条归因计数）。都走 `ix_bad_cases_workspace_created` / `ix_bad_cases_workspace_object` / `ix_bad_cases_workspace_type`，扫描面由空间 bad case 数决定。
- 响应不是一个快照：四个端点各自开读会话，同一屏内可能存在毫秒级不一致（例如刚上报一条时 summary 已含、list 尚未含）。与 m8-02 的列表/计数取舍相同，读多写少，本 issue 不引入快照或事务级一致性。
- `sessions` 含 pending 根，与 Session 页的 `pendingSessions`、`total` 不是同一集合，页面文案不能把三者相加；这是有意的口径分工，已写进 06 §7.5、05 §3.10/§4.18 与 OpenAPI 描述。
- `used` 可能大于 `quota`（legacy 目录同步可推过额度），也会大于窗口内的 `badCases`；前端展示额度时不能假设 `used <= badCases`。
- `attributionCount` 目前只可能是 0/1（表结构一 case 一归因行），测试覆盖了 0、1 与 `object_version IS NULL` 的三元组；distinct 三元组去重路径在 m10 放宽 `uq_bad_case_analysis_case` 之前无法被集成测试证伪（同一 case 接两个 probe 的语料构造不出来），当前只保证 SQL 形状正确，m10 落地时必须补一条「同 case 两个 probe、三元组相同只算 1」的反向用例。
- `triggerAt == createdAt` 是过渡事实：m9-04 补上对象触发点坐标后，同一个字段会开始返回真实触发时间且不再等于 `createdAt`；前端不应把它当排序键或相等判断依据。
- 列表分页用 `OFFSET`，深翻页在超大空间会线性变慢；空间额度（默认几十到几百条）下不是问题，若未来单空间上万条再改成 keyset 分页。
- 表存在性探测按 repository 实例缓存：运行中建表/删表需要重启进程才会重新探测，与既有 Session 读路径一致；首次探测时缺失才会降级，运行中删表可能直接抛数据库错误，因此不承诺「任何时刻都不 500」。
- MySQL 侧由 CI 的 mysql lane 执行 `test_database.py` 的 `@pytest.mark.mysql` 用例，其中新增一条 overview repository 用例覆盖 summary/trend/sources/list 的 `SUM(CASE)`、`COUNT(DISTINCT)` 与 distinct 子查询；本地无 MySQL 服务时该用例 skip，本地只跑了 SQLite。
- 本 issue 不含目标视角（`/overview/targets*`）、图表组件与前端页面，也不新增迁移；三者分别在 m11、m8-04 与后续 issue 内落地。
