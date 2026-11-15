# 15 · V1 / V2 差距与实现改动地图

> 本文回答：当前实现相对 V1 原型缺什么、V2 原型相对 V1 改了什么、V2 落地时应改哪些既有文档与代码边界。
> 基线：[V1 原型](../14-15-ui-prototype/harness-evolution.html) · [V1 设计](README.md) · [V2 原型](../ui-prototype-v2/harness-evolution.html) · [V2 原型验收说明](../ui-prototype-v2/design-v2.md)。

## 1. 判定方法

对比分三类：当前实现与 V1 原型的可观察差异、V2 原型相对 V1 的产品与交互增量、以及把 V2 目标态落回当前代码时需要调整的设计边界。

当前实现以 `apps/api`、`apps/web`、`packages/contracts` 的已合入行为为准；V1 原型是交互与信息层级基线，不把原型中的打桩数据、展示号和模拟推进当作生产能力。

## 2. 当前实现与 V1 原型

### 2.1 已对齐

| 范围 | 结论 |
|---|---|
| 应用壳 | 亮色设计令牌、顶栏双入口、数据同步浮层、Session 与自进化的信息密度一致 |
| Session 页 | 左侧列表、筛选、排序、状态点、统计条、双密度条、右侧概览与 Agent 执行流均保留 |
| 错误详情 | 左右分栏、执行流按问题过滤、问题描述与归因分析双 Tab、深链恢复选中态均保留 |
| 自进化 | 运行分组、目标/版本/时间段筛选、命中确认、仅聚类入口、六步详情、对象配置和执行日志均有实现骨架 |
| 权限 | 登录、首登改密、access/refresh token、路由守卫与管理员操作边界已实现 |

### 2.2 有意差异

| 差异 | 当前实现 | 原因 |
|---|---|---|
| 时间线 | 原型保留“打开时间线”按钮；当前实现不提供 | V1 设计已裁撤完整时间线，只保留 `user_turns` 输入锚点 |
| ID 展示 | 原型使用 `I-*` / `R-*` 展示号；当前使用真实 ID 并截短 | 真实 ID 深链避免展示号与业务主键双轨 |
| 根会话 ID | 当前列表卡与概览均展示 root session ID | `13-root-session-id.md` 的增补要求 |
| 模拟推进 | 原型有演示按钮；当前不提供 | 生产流程由后台任务自动推进 |
| 对象配置、执行日志 | 原型没有完整页面；当前有 | V1 设计新增的后端闭环能力 |

### 2.3 仍需修正或补齐

| 缺口 | 现状 | V2 处理 |
|---|---|---|
| 归因粒度 | 一个 bad case 仍只有一条 `bad_case_analysis → probe_reports` 结果 | `bad_case_analysis` 改为多行关联，错误详情承载多条对象版本归因 |
| Session 首屏 | 默认请求 `limit=100`，搜索为防抖查询 | 默认最新 10，只有回车才重新查询 |
| 密度文案 | 当前 UI 显示“/百消息”，V1 原型显示“/百步” | V2 统一用户文案为“步骤”，后端字段可继续使用现有 message 分母；若产品决定改口径，必须同时改设计、API 字段和迁移，不能只改标签 |
| 目标目录容错 | 一个不可访问仓库会让 `GET /catalogs/targets` 整体 422 | 对象配置列表与版本读取拆开；单个版本失败只影响对应对象的版本控件 |
| 用户与权限界面 | 当前只有用户 API 与顶部用户菜单 | V2 增加空间成员和角色管理；全局用户目录仍不开放注册 |
| 占位执行能力 | patch 内容、评测和终评为占位；Git candidate 链路为真实骨架 | V2 不改变占位边界，但 run 输入、候选、归因和聚类改为真实持久化 |

结论：当前实现已经完成 V1 的主体 UI 与 API 骨架，V1 原型中的主要未对齐项要么是有意裁撤，要么是有明确后续边界的占位能力；真正阻塞 V2 的是空间隔离、多归因、上报额度和潜在策略。

## 3. V2 原型相对 V1 原型

| 能力 | V1 | V2 |
|---|---|---|
| 身份 | 单组织、登录即可见全部数据 | 唯一全局管理员、普通用户、空间角色；不开放注册，保留 AuthProvider/Cookie/SSO 接入缝 |
| 导航 | Session / 自进化 | 工作空间切换 + 总览 / Session / 自进化 / 空间管理 |
| 数据归属 | bad case 全局共享 | bad case 归属工作空间；Session 是所属空间 bad case 的根会话投影 |
| 写入入口 | 外部同步写入 | 空间独立上报地址与凭据，POST body 即 bad case 类型，额度在写入事务内校验 |
| 总览 | 无 | bad case 与进化对象双视角，支持对象多选、时间粒度、self/discovery 堆叠趋势、分页与下钻 |
| Session 列表 | 一次拉取并实时筛选 | 默认最新 10；输入 session ID 回车查询，未命中双侧空态 |
| 自进化输入 | 预先存在的 probe 报告 | 空间 bad case → 对象出现过的 Session → 全部关联 case → 触发点与潜在策略 |
| 归因 | 错误详情中的单条结论 | run 内按对象版本生成，一个 case 多条归因，支持缓存与“非该对象问题” |
| 运行流程 | 六步 | 七步：范围、Session、潜在、归因、聚类、迭代、终评 |
| 错误详情 | 错误卡列表 + 单归因 | 可折叠 bad case 组 + 归因分页子项 + 归因详情深链 |
| 权限 | 全局 admin/member | 全局 admin 负责空间与空间管理员；空间管理员负责本空间；成员与只读按能力收口 |

## 4. 设计文档需要修改的位置

| 文档 | 修改 |
|---|---|
| `01-architecture.md` | 从单组织共享改为工作空间权限边界；增加上报、总览、AuthProvider、候选、潜在匹配与七步链路 |
| `02-features.md` | 增加 F21–F27；修正 F3/F5/F6/F8/F9/F10/F11/F13/F15/F19 的 V2 口径 |
| `03-frontend-architecture.md` | 增加空间路由、空间切换器、总览、多归因组件和 queryKey 空间前缀 |
| `04-backend-architecture.md` | 增加 workspaces/overview 服务、上报凭据边界、归因引擎与空间依赖 |
| `05-api-design.md` | 增加空间、成员、凭据、上报、总览、预览、多归因 DTO 与端点；修正事件读取方法和错误码 |
| `06-database-design.md` | 新增空间三表与候选表；原位扩展 `bad_cases`、`bad_case_analysis`、`probe_reports`、`targets/runs/events`、`agents/agent_events` |
| `07-backend-implementation.md` | 增加空间服务、权限依赖、事件触发坐标、潜在匹配、归因缓存、七步 prepare 与代码切片 |
| `08-frontend-implementation.md` | 增加空间壳、总览、最新 10、多归因左栏、四步向导、七步详情与迁移路由 |
| `09-review-guide.md` | 追溯矩阵切换到 V2；移除旧 probe 流程作为主路径的表述；增加差距与迁移检查 |

## 5. 数据库复用规则

V2 遵循“既有表优先原位演进，新表只承载全新粒度”：

| V1 表 | V2 处理 |
|---|---|
| `bad_cases` | 加 `workspace_id`；成为空间上报、总览、Session 投影和潜在匹配的主输入 |
| `bad_case_analysis` | 删除 case 唯一约束，增加 `(bad_case_id, probe_id)` 唯一；表达一 case 多归因关联 |
| `probe_reports` | 保留主键和描述列；增加 workspace、conclusion、confidence、缓存键、首次/最近 run 与复用计数 |
| `probe_clusters` | 保留表名和 `probe_cluster_*` 列名；聚类类型由归因 `attribute_type` 驱动 |
| `probe_cluster_probes` | 保留表名和 `probe_id`；成员继续指向归因明细 |
| `evolution_targets` | 加 `workspace_id`，唯一键改为 `(workspace_id, object_type, object_name)` |
| `evolution_runs` | 加 workspace、潜在策略和缓存开关快照 |
| `evolution_run_events` | 加 workspace 冗余审计；step_index 扩到 0–6 |
| `agents` / `agent_events` | 加 `tree_index`、`triggered_at`、`object_version`，为版本化和稳定的触发点比较提供坐标 |

只新增 `workspaces`、`workspace_members`、`workspace_ingest_credentials` 和 `evolution_run_candidates`。不新增与归因、簇成员、targets、runs 重叠的表。

## 6. 代码改动地图

### 6.1 契约与数据库

- `packages/contracts` 先加入 Workspace、Member、Credential、Overview、Ingest、Attribution、PotentialPolicy、AttributionPreview 与 V2 七步类型。
- Alembic 分两次迁移：先空间与关联列，再归因/缓存、候选和触发点列；每个迁移都必须支持 SQLite batch 与 MySQL。
- `bad_cases` 加 `workspace_id` 后先回填默认空间再收紧 NOT NULL；`bad_case_analysis` 先建 `(case, probe)` 唯一索引，再删除 case 唯一约束。
- `probe_reports.cache_key` 由服务计算并用于原子 upsert；不能用 case 之外的字段拼接后产生跨空间冲突。

### 6.2 后端

- 新增 `service/workspaces`、`api/workspaces.py`、`api/ingest.py`、`api/deps.py`；所有空间资源进入服务前先校验“可见空间 + 最低角色”。
- `auth/session` 聚合当前用户和可用空间；`/api/users` 保留全局用户管理，但禁止创建第二个全局管理员。
- `service/acquisition` 归一化补 `tree_index`、`triggered_at`、`object_version`；parser version 升级并支持回放。
- `service/overview` 按 workspace 过滤，聚合来源、时间桶、self/discovery 和归因三态；所有列表使用 SQL 分页。
- `service/evolution/potential.py` 成为预览、run prepare、总览的唯一匹配实现；只按目标版本精确关联，版本未知的 Session 跳过并计入 `versionUnresolvedSessions`。
- `service/evolution/attribution.py` 负责缓存读写、upsert、复用计数与候选关联；归因引擎保持纯函数边界。
- `service/sessions` 与 `service/problems` 所有读写加 workspace 约束；Session 成员关系通过 bad case 投影，不在轨迹表复制空间列。

### 6.3 前端

- 路由迁到 `/workspaces/:wid/...`，旧路由只做有权限的最近空间重定向；切换空间时清空旧空间 query cache。
- `TopNav` 增加空间切换器和空间管理入口；`auth/session` 是启动时唯一身份/空间恢复入口。
- `SessionPage` 初次请求 limit=10，搜索改为 Enter 或按钮提交；未命中时列表和概览都显示空态。
- 新增 `pages/overview`，复用 V1 的 statstrip、card、table、pager 和颜色令牌；图表采用自研 SVG，不引入第二套图表设计系统。
- `ErrorSidebar` 改为 `CaseGroup` 列表，每组携带归因总数、页码、展开状态；`AttributionReport` 支持多条归因和触发点对照。
- `LaunchWizard` 从两步扩为四步：范围/策略、Session 关联、潜在 bad case、归因预览与缓存开关。
- `RunDetail` 从六步扩为七步；历史 V1 run 由后端兼容映射为相同的七步 DTO，前端只渲染后端给出的 step 列表。

## 7. 实施顺序

1. 契约与迁移：空间表、workspace 列、分析多归因关联、probe 缓存字段、候选表、触发点列。
2. 身份与权限：auth/session、AuthProvider 接缝、空间成员依赖、对象配置空间隔离。
3. 上报链路：凭据、额度事务、bad_cases.workspace_id、上报后轨迹补齐。
4. 空间 Session 与总览：投影查询、时间桶、来源聚合、组合筛选分页。
5. 自进化：触发点回放、PotentialMatcher、归因缓存、预览端点、七步 prepare 与详情。
6. 前端：空间壳、总览、Session 最新 10、四步向导、七步详情、多归因错误详情。
7. 兼容与退役：旧路由重定向、旧 probe 读接口适配、历史 run 回放、数据清理与监控。

## 8. 验收重点

- 同一用户只能看见有成员关系的空间；空间管理员不能任命或修改空间管理员，全局管理员可以；不可见空间统一 404。
- 上报重复 ID 不增加额度，跨空间凭据失败，额度满时旧数据不丢。
- Session 关联必须按对象版本精确匹配；版本未知的历史数据单独计数并跳过，不会被展示成版本精确命中。
- 向导预览、运行 prepare 和总览使用同一潜在匹配实现，三处数量一致。
- 缓存关闭时重算并覆盖同键结果，缓存开启时复用最近成功结论并增加复用计数；“非该对象问题”不进入簇但出现在错误详情。
- 错误详情一个 case 的多条归因可分页、可通过 `case/tab/at` 深链恢复，切换空间不会复用旧空间缓存。
