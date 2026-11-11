# 16 · V2 工作空间总览与 Session 列表

> 本文回答：工作空间总览页（bad case 总览 / 进化对象总览双视角）看什么、聚合口径与接口怎么定、Session 错误查看页的「最新 10 条 + 回车查询」怎么改。
> 前置：[15 工作空间](15-v2-workspaces.md)（空间模型与权限）；配套：[17 归因](17-v2-attribution.md)（潜在 bad case 与归因口径）。
> 验收基准：[V2 原型](../ui-prototype-v2/harness-evolution.html) 总览页（`v2RenderOverview` / `v2RenderTargetsOverview` / `v2TargetDetailCard`）。

## 1. 背景与目标

V1 没有 Dashboard：登录后直接进 Session 列表，问题数据只能按会话逐个看。V2 给每个工作空间一个总览页，回答三个问题：

1. 这个空间的 bad case 总量、`self`（自身存在问题）/ `discovery`（发现前置步骤问题）构成、时间趋势如何？（目标态第 4 点前半）
2. 按不同 `bad_cases.object_name`（bad case 上报来源）分别是什么情况？——多选筛选，不选即全部。
3. 从时间、来源、类型任意组合下钻到具体 bad case，一键进入 Session 错误详情对应问题。

同时把 Session 错误查看页的默认行为从「全量拉取 + 实时过滤」改为「最新 10 个 + 回车精确查询」（目标态第 5 点）。

页面文案映射（展示层统一，字段原名不变）：`self` → 「自身存在问题」；`discovery` → 「发现前置步骤问题」；`object_name` → 「bad case 上报来源」。

## 2. 口径定义（总览的所有数字都从这里推导）

| 口径 | 定义 |
|---|---|
| 空间 bad case 集合 | `bad_cases WHERE workspace_id = :wid`；额度 `used` = 该集合 `COUNT(*)`（[15 W3](15-v2-workspaces.md)） |
| 空间 Session 集合 | 上述集合的 `DISTINCT bad_case_session_id` **投影**（轨迹表不加空间列，[15 W2](15-v2-workspaces.md)）；其中已归一化的 = `JOIN session_families` 命中的行，其余计入「待轨迹同步」 |
| 上报来源数 | 空间 bad case 集合的 `DISTINCT object_name` 数 |
| self / discovery 数 | 按 `bad_case_type` 分组的 `COUNT(*)` |
| 时间桶 | 按 `bad_cases.created_at`（上报时间）分桶，粒度 `day / week / month`；周按 ISO 周（周一起），桶边界用 Asia/Shanghai 时区计算 |
| 关联 Session（对象视角） | 该对象（`object_name@version` 或按对象名聚合时仅 `object_name`）在空间 Session 集合内**出现过触发点**的 Session 数（触发点定义见 [17 §3](17-v2-attribution.md)；按对象名聚合时不区分版本） |
| 潜在 bad case（对象视角） | 该对象在关联 Session 内按**默认潜在策略**命中的 bad case 数；与向导/run 完全同一实现（[17 §4](17-v2-attribution.md)），查询时计算，不落列 |
| 是该对象 / 非该对象 / 未分析 | 该对象已有 `bad_case_attributions` 中 `conclusion=attributed` / `non_target` 的去重 bad case 数；无归因记录的潜在 bad case 为「未分析」（[17 §5](17-v2-attribution.md)） |

- **潜在口径一致性是硬约束**：总览、向导预览、run 详情三个入口共用同一个 `PotentialMatcher` 服务；总览不得另造近似口径，否则「总览潜在数 ≠ 运行潜在数」会立刻被用户发现。
- 潜在匹配需要读 `agent_events`（触发点比较），成本中等：实现按 `(workspace, object, window)` 做 60s 进程内缓存；空间量级（数百对象 × 数千 bad case）下可接受，缓存失效由上报写入路径顺带清除。

## 3. bad case 总览（一级 Tab）

### 3.1 指标条（statstrip，6 项）

bad case 总数 · 自身存在问题 · 发现前置步骤问题 · 关联 Session · bad case 上报来源数 · 额度使用（`used / quota`）。全部由 `GET .../overview/summary` 一次返回（静态元数据聚合，符合 [05 §1.1](05-api-design.md)）。

### 3.2 趋势与分布

- 时间选择：近 7 / 30 / 90 天或自定义区间；粒度日 / 周 / 月。
- 「bad case 上报来源」多选下拉：不选 = 全部；多选 = 并集；选中项以 chip 展示、可逐项移除。
- 主图：按时间桶堆叠 self（蓝）/ discovery（紫）柱状图，Y 轴取桶内最大值刻度。
- 来源分布：按 `object_name` 汇总总量与 self/discovery 占比（原型 top6 条形）。
- 明细矩阵：来源 × 时间桶的展开表格（可折叠）。

## 4. 进化对象总览（二级 Tab）

与 bad case 总览共享空间与时间上下文（切换 Tab 不重置时间窗），布局对齐原型：

- 指标条：对象数 · 关联 Session · 潜在 bad case · 已分析（是该对象 / 非该对象）· 未分析。
- 趋势图：多选进化对象 + 「查看信息」三态 chip（是该对象 / 非该对象 / 未分析）控制堆叠信息。
- 分布块：「不同进化对象的关联 Session」（含潜在 / 仅关联两段）与「不同进化对象的潜在 bad case」，柱长按最大值归一。
- 右侧对象列表：每页 5 条，按「可进化潜在 bad case 数量（是该对象 + 未分析）」降序；每项显示对象/版本、关联 Session、潜在数、可进化数；空间管理员可直接新增/编辑/移除（复用 targets CRUD，[15 §3.4](15-v2-workspaces.md)）。
- 底部潜在 bad case 列表：8 条/页；筛选 = 进化对象（多选）+ 上报来源 + 状态（是/非/未）+ 时间段；已分析行展示归因 ID，点击跳该 bad case 的归因分析 Tab（`?case=&tab=attr&at=`，[17 §9](17-v2-attribution.md)）。
- 单个进化对象分析卡：对象下拉必选 + 版本多选（默认最近 5，5/10/20/全部）+ 独立时间段；按版本的三态（是/非/未）分布与来源去重分布。

## 5. Session 错误查看改造（目标态第 5 点）

### 5.1 口径与接口

- 列表 = **当前空间**的 Session 集合（§2 投影），按 `started_at` 倒序取前 10；标题显示「最新 10 / 总数 N」。
- `GET /api/workspaces/{wid}/sessions?q=&status=&sort=&limit=10`：`limit` 默认从 100 改为 10（上限仍 500）；`q` 语义不变（标题/仓库/根会话 ID 的前缀与子串，[13 §4](13-root-session-id.md)）；**响应新增 `total`**（该空间命中筛选的 Session 总数），`items` 为当前页。
- 搜索交互：输入 root session ID（或标题/仓库关键词）**回车触发**重新查询；清空回车恢复最新 10；未命中时左右两栏都显示空态，不保留旧选中。V1 的 300ms 防抖实时查询移除（数据量大时逐键全表扫不合适）。
- 选中 Session 后才加载概览/执行流/问题列表（现有三接口不变，只加空间校验）。
- 空间内 Session 的状态 chips / 排序保持 V1 行为。

### 5.2 与 V1 的行为差异清单

| 项 | V1 | V2 |
|---|---|---|
| 默认拉取 | 全量（limit=100 固定） | 当前空间最新 10（响应带 total） |
| 搜索 | 防抖实时过滤 | 回车触发；清空回车恢复 |
| 空态 | 空列表提示 | 左右两栏独立空态（「未找到该 Session」） |
| 未选中 | 自动选第一个 | 保持（命中结果中的第一个） |

## 6. API 契约（全部挂 `require_workspace_role(wid, viewer)`，[15 §2.4](15-v2-workspaces.md)）

| 端点 | 说明 |
|---|---|
| `GET /api/workspaces/{wid}/overview/summary?from=&to=&objects=` | 指标条 6 项 + 时间窗回显；`objects` 为空即全部 |
| `GET /api/workspaces/{wid}/overview/trend?from=&to=&grain=day\|week\|month&objects=&types=` | `{ buckets: [{ bucket, self, discovery, byObject: [{object, self, discovery}] }] }`；`types` 可选 `self/discovery` 子集 |
| `GET /api/workspaces/{wid}/overview/sources?from=&to=&objects=` | 来源分布 `{ items: [{object, total, self, discovery}] }`（矩阵由前端用 trend 数据拼装，不单独出接口） |
| `GET /api/workspaces/{wid}/bad-cases?from=&to=&objects=&badCaseType=&page=&pageSize=8` | 组合筛选分页列表（时间段/来源/类型全部可空 = 不限）；`items[]` 为 `BadCaseListItem` + `total` |
| `GET /api/workspaces/{wid}/overview/targets?from=&to=&page=&pageSize=5` | 对象列表（关联 Session/潜在/是/非/未/可进化排序 + targets 配置字段） |
| `GET /api/workspaces/{wid}/overview/targets/trend?from=&to=&grain=&targets=&states=` | 对象多选 + 三态（isTarget/nonTarget/unanalyzed）趋势 |
| `GET /api/workspaces/{wid}/overview/targets/cases?targets=&objects=&status=&from=&to=&page=&pageSize=8` | 潜在 bad case 列表（含归因 ID 与结论状态） |
| `GET /api/workspaces/{wid}/overview/targets/{targetId}/detail?versions=&from=&to=&versionLimit=5` | 单对象分析卡：按版本三态分布 + 来源去重分布 + 统计 |

- `BadCaseListItem`：`badCaseId/sessionId/sessionTitle/objectName/objectType/objectVersion/badCaseType/title/createdAt/attributionCount`（`attributionCount` 供列表直接显示归因数，DISTINCT 对象·版本）。
- 时间参数一律 `from/to`（日期或 RFC3339 均可，服务端归一为 Asia/Shanghai）；`grain` 封闭集合 `day|week|month`，非法 422。
- 下钻深链：`/workspaces/:wid/sessions/:sid/errors?case={badCaseId}&tab=desc`（行内 ID 链接新窗口打开；整行不可点击，沿 [原型第十七轮决策](../.agents/notes/implemented/bug-fix/2026-11-11-ui-prototype-v2-ui-polish.md)）。
- 新增错误码：`GRAIN_INVALID`（422，粒度非法）。

### 6.1 趋势分桶的实现约定（跨方言）

分桶 SQL 在 repository 层按方言适配（现有 `Database` 接口模式）：MySQL 用 `DATE_FORMAT(created_at, '%Y-%m-%d')` / `YEARWEEK(..., 3)` / `'%Y-%m'`，SQLite 用 `strftime`；服务层只做参数归一与结果拼装，不含方言字符串。空桶由服务端按时间窗补零后返回（前端不插值）。

## 7. 前端（代码改动地图）

| 改动 | 位置 | 内容 |
|---|---|---|
| 新页面 | `pages/overview/Index.vue` | 双 Tab（bad case 总览 / 进化对象总览）；statstrip、筛选条、堆叠柱图（自研 SVG，沿用 V1 蓝/紫 token）、来源分布、明细矩阵、分页列表 |
| 进化对象总览组件 | `pages/overview/components/TargetsOverview.vue` + `TargetDetailCard.vue` | §4 全部内容；对象编辑复用 targets 表单弹窗 |
| 路由 | `/workspaces/:wid/overview` | 空间默认落地页；URL 同步 `?tab=&range=&grain=&objects=` |
| Session 页 | `pages/sessions/*` | SearchBox 改回车提交 + 「最新 10 / 总数」标题 + 双空态；`useSessionList` 走空间前缀接口 |
| queryKeys | `api/queryKeys.ts` | `["ws", wid, "overview", …]`、`["ws", wid, "sessions", filters]`；切空间整树失效 |
| composables | `api/overview.ts` + `useOverview.ts` | §6 各端点；trend 数据驱动图表 |

## 8. 测试与验收

- 指标条与列表 total 与 SQL 手算一致；时间桶边界（跨月/跨周）正确；空窗补零。
- 来源多选（不选=全部）与列表筛选互相独立（原型行为）；分页 8 条/页。
- 下钻深链在新窗口恢复到对应 bad case 问题描述 Tab。
- Session 列表：默认 10 条 + total；回车查询命中替换、清空恢复、未命中双空态。
- 进化对象总览：潜在数与向导预览（同条件）一致（共用 PotentialMatcher 的回归用例）。
- `pnpm test:api` 聚合口径用例；`pnpm test:e2e -- --pattern overview` 冒烟。

## 9. 非目标

- 自定义图表类型（折线/饼图切换）、导出 CSV。
- 总览数据的物化/预聚合表（量级未到；缓存先行）。
- 跨空间汇总视图（全局管理员也按空间逐个看）。
- 「查看信息」三态过滤对分布块的联动（原型第十四轮已定为只过滤趋势图）。

## 10. 已确认决策

| # | 决策 | 依据 |
|---|---|---|
| O1 | 空间 Session 集合 = bad case 投影，不物化、不加轨迹侧空间列 | [15 W2]；与原型 used 统计口径一致 |
| O2 | 潜在 bad case 口径在总览/向导/run 三处共用同一实现 + 60s 缓存 | 口径漂移会被直接对比发现 |
| O3 | Session 列表默认 limit 10 + 响应加 total；搜索回车触发 | 目标态第 5 点；保留 q 三类匹配语义 |
| O4 | 趋势按 `created_at` 分桶、ISO 周、Asia/Shanghai；分桶 SQL 走方言适配 | 上报时间是最直观的业务时间轴 |
| O5 | 下钻 = 行内 ID 深链（新窗口），整行不可点 | 原型第十七轮决策，防误触 |
| O6 | 总览二级 Tab 只做 bad case / 进化对象两个视角 | 原型验收范围；不扩图表种类 |
