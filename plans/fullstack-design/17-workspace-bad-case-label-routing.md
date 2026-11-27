# 17 · 公共 badcase 按 label 划分工作空间

> 本文回答：平台定期从一个公共 badcase 仓库拉取数据后，如何依据 `items[].meta_data.label` 把同一条 badcase 同时提供给多个工作空间，并让列表、Session、统计和自进化使用同一空间边界。
> 前置：[05 接口设计](05-api-design.md) · [06 数据库设计](06-database-design.md) · [07 后端实现](07-backend-implementation.md) · [08 前端实现](08-frontend-implementation.md) · [12 公共目录同步](12-bad-case-catalog-sync.md)。

## 1. 目标与边界

生产 badcase 统一进入公共仓库，平台沿用 `bad_case_catalog_sync` 的启动即跑、定时分页、全局 `bad_case_id` 游标、单飞和失败状态。空间管理员在空间管理中维护当前空间接受的 label；一个 label 可以配置给多个空间，一条公共 badcase 原始事实只保存一次，但可以同时关联多个空间。

本切片同时保留空间凭据直接上报：直接上报为目标空间建立 `direct_ingest` 关联，公共目录为所有匹配空间建立 `catalog_label` 关联。所有空间读路径只认关联表，不再把 `bad_cases.workspace_id` 当作可见性事实。既有字段暂留作直接上报所有权兼容，待兼容窗口结束后再移除。

不改上游 `/bad-cases` 接口，不要求上游支持 label 参数，不推断缺失 label，不建立 label 字典，不回写公共仓库，不追溯修改已经创建的自进化运行输入。当前游标只能看到新 ID；本切片把 label 视为创建后不可变，重试或冷启动再次收到同一 ID 时仍会重新对账。若上游需要修改历史 label，应先扩展为 `updated_at` 增量契约。

## 2. 数据模型

### 2.1 `workspace_bad_case_labels`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `workspace_id` | `VARCHAR(36)` | PK/FK → `workspaces.id`，级联删除 | 配置所属空间 |
| `label` | `VARCHAR(128)` | PK | 区分大小写的精确值 |
| `created_at` | 带时区时间 | NOT NULL | 首次配置时间 |
| `updated_at` | 带时区时间 | NOT NULL | 最近确认时间 |

服务拒绝空串、首尾空白、超过 128 字符和重复值。一个 label 可出现在多个 workspace 行中。

### 2.2 `workspace_bad_cases`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `workspace_id` | `VARCHAR(36)` | PK/FK → `workspaces.id`，级联删除 | 可见空间 |
| `bad_case_id` | `VARCHAR(64)` | PK/FK → `bad_cases.bad_case_id`，级联删除 | 公共事实 ID |
| `assignment_source` | `VARCHAR(24)` | PK | `legacy_owner` / `direct_ingest` / `catalog_label` |
| `label` | `VARCHAR(128)` | NULL | `catalog_label` 的命中值，其余为空 |
| `assigned_at` | 带时区时间 | NOT NULL | 关联建立时间 |

同一空间与 badcase 可以同时有直接上报和 label 两种来源；读取使用 `EXISTS` 或 `SELECT DISTINCT workspace_id,bad_case_id`，不重复计数。删除 label 规则只删除对应的 `catalog_label` 行，直接上报关联继续保留。

迁移创建两表及索引，并把每条既有 `bad_cases.workspace_id` 回填为关联：`origin='report'` 的行为 `direct_ingest`，`origin='catalog'` 的行为 `legacy_owner`；同时把存量 catalog 行的 `meta_data.label` 按 label 契约投影到 `catalog_label`（合法值保留，非法或缺失为 `NULL`），并把 `catalog_synced` 置真。存量公共事实因此无需重放游标即可参与新增 label 规则；重复执行回填保持幂等。后续直接上报同 ID 时把同空间的 `legacy_owner` 收敛为 `direct_ingest`；公共目录再次触达同 ID 时移除其 `legacy_owner`，再依据 label 建立 `catalog_label`，避免旧默认空间继续看到公共数据。

### 2.3 `bad_cases.catalog_label`

`bad_cases` 新增可空 `catalog_label VARCHAR(128)` 与索引。它是公共同步从 `meta_data.label` 验证后提取的查询投影，不是第二事实源：目录同步每次 upsert 都同时覆盖该列；直接上报固定写 `NULL`。空间规则重算和未分配统计只查询该列，不在 SQL 中解析 JSON，从而保持 SQLite/MySQL 行为一致并使用索引。

## 3. label 契约

`meta_data` 必须是对象且 `meta_data.label` 必须是长度 1–128、无首尾空白的字符串。匹配区分大小写，空间配置多个 label 时为 OR。同一 label 对应多个空间时，每个空间都获得关联。

缺少 `meta_data`、缺少 label、`null`、空串、含首尾空白、超长或非字符串均为 invalid，`catalog_label` 写 `NULL`；公共事实仍落库，删除已有 `catalog_label` 关联，不进入默认空间。合法但没有任何空间配置的值为 unassigned。同步状态新增 `assigned_count`、`unassigned_count` 与 `invalid_label_count`，计数针对最近一次完成页提交后的公共事实状态。

## 4. 写入与重算

### 4.1 公共目录同步

`BadCaseCatalogSyncService` 的分页、预算与游标不变。Repository 的单页事务按以下顺序执行：

1. upsert `bad_cases` 公共事实；
2. 对本页 ID 删除 `legacy_owner` 与旧 `catalog_label` 关联；
3. 解析合法 label，连接 `workspace_bad_case_labels`，批量 upsert 所有匹配关联；
4. 更新游标和 assigned/unassigned/invalid 统计；
5. 提交后才允许下一页推进。

任何一步失败整页回滚，游标不前进；重试产生相同事实和关联。目录同步不按空间配额丢弃匹配项，因为游标推进后无法可靠补回。空间 `used` 改为关联表中去重 badcase 数；公共分配可使 `used > quota`，此时直接上报继续返回 `QUOTA_EXCEEDED`，空间管理提示调整额度或移除 label。

### 4.2 空间直接上报

直接上报保持现有凭据、URL、全局 ID 冲突和事务额度校验。插入或更新公共事实后，为目标空间 upsert `direct_ingest` 关联；同空间既有 `legacy_owner` 删除。额度检查和返回的 `workspace_used` 都按关联表去重计数。

### 4.3 配置保存与历史重算

API 以完整集合替换当前空间 label。一个数据库事务校验并锁定 workspace、替换规则、删除该空间全部 `catalog_label` 关联，再以 `bad_cases.catalog_label JOIN workspace_bad_case_labels` 的 `INSERT … SELECT` 批量重建。新增规则补齐历史数据、删除规则撤销实时可见性；不回退 catalog 游标、不请求外部平台，也不触碰 `direct_ingest` 或既有运行候选。保存响应只在整个事务提交后返回，因此读取不会观察到已保存规则与关联集合不一致的状态。

## 5. 统一读取边界

`WorkspaceReadScope` 增加 badcase 关联子查询，所有空间化读取通过它约束：

- badcase 列表、详情、归因进度；
- Session 列表、Session 内 badcase 与轨迹补齐状态；
- 工作空间总览、来源和对象统计；
- 自进化 Session 关联、潜在 badcase、归因候选与缓存报告；
- workspace `used`、额度检查和同步状态。

已持久化的 `evolution_run_candidates`、`probe_reports.workspace_id` 和运行快照不反查实时关联，因此配置变化只影响后续预览和新运行，已有运行可继续恢复。

归因进度聚合按请求空间匹配 `probe_reports.workspace_id`，不跟随 `bad_cases.workspace_id`：一条 label 共享的公共 case 在空间 B 产出的报告只计入 B，不会因为事实行仍归默认空间而错算到默认空间；全局管理员视图不限制报告空间。

## 6. API

### `GET /api/workspaces/{wid}/bad-case-labels`

空间成员可读，返回 `{ "items": ["code-review", "tool-use"], "assignedBadCaseCount": 142 }`。`assignedBadCaseCount` 是该空间所有来源（`legacy_owner` / `direct_ingest` / `catalog_label`）去重后的可见 case 数，不等于 label 命中数；清空规则只撤销 `catalog_label` 关联。

### `PUT /api/workspaces/{wid}/bad-case-labels`

空间管理员或全局管理员可写，请求 `{ "items": ["code-review", "tool-use"] }`。`items` 为必填字段：省略或传 `{}` 返回 422，`[]` 表示显式清空全部规则。服务端排序、去重后以完整集合原子替换并完成历史重算；非法项返回 422，空间不存在返回 404，权限不足返回 403。响应为上述资源。

### `GET /api/workspaces/{wid}/bad-case-labels/suggestions`

空间成员（viewer 及以上）可读公共目录词表，返回 `{ "items": [ { "label": "review", "badCaseCount": 12 } ] }`。`q` 是可选、大小写不敏感、最长 128 字符的前缀；`limit` 取 1–50，默认 20。`q` 为空或省略时返回出现次数最多的前 N 个，结果始终按 `badCaseCount` 降序、同数按 `label` 字典序，`%` 与 `_` 按字面量匹配（复用会话搜索的 LIKE 转义）。计数与排序按精确 label 值聚合：SQLite 默认 BINARY 区分大小写，MySQL 在分组与排序上使用 `utf8mb4_bin`，两端一致，`Review` 与 `review` 是两行各自计数；候选排除 `catalog_label` 为 NULL 与空串的行。词表来自 `bad_cases.catalog_label` 的有效值聚合，不按当前空间的规则收窄——配置 label 前该空间本就看不到任何 case——也不读取其他空间的规则集合。未认证返回 401，空间不可见返回 404，非法 `limit` 返回 422。

## 7. 空间管理 UI

V2 原型的 190px 左侧管理导航新增「Badcase 类型」，位置在「上报接入」之后、「归因 Skill」之前。内容沿用 `.admin-head`、`.admin-content`、`.ingest-card`、`.admin-table`、`.btn` 和现有亮色令牌：

```text
┌ Badcase 类型 ───────────────────────────── [保存配置] ┐
│ 选择当前空间从公共仓库接收的 badcase 大类型。          │
│                                                       │
│ 已配置 label                                           │
│ [ code-review × ] [ tool-use × ]                       │
│ [ 输入 label________________ ] [添加]                   │
│                                                       │
│ 当前划分                                               │
│ 已关联 142 条                                          │
│ 未配置 label 时，公共 badcase 不会进入当前空间。       │
└───────────────────────────────────────────────────────┘
```

标签按字典序展示；Enter 与「添加」执行相同行为；重复、空白和非法长度在输入旁提示；未保存修改显示“有未保存更改”。保存成功提示“Badcase 类型已保存，历史数据已重新划分”，并刷新 workspace、总览、Session 和自进化相关 query。viewer/member 可查看但不能编辑；加载、错误和空配置沿用现有状态组件。移动端管理导航横向滚动，内容不溢出。

输入框带自绘候选下拉，不引入 Element Plus 弹层：聚焦且输入为空时展示出现次数最多的 Top N，输入变化经 200ms 防抖按大小写不敏感前缀查询；本地已加载候选同时按当前输入做大小写不敏感前缀过滤，输入变化后旧候选立即隐藏。每项左侧是 `label`、右侧以弱化样式显示 `N 条`，已加入草稿的 label 不再出现。点击候选、或方向键高亮后 Enter，只把该 label 加入草稿（不保存、不触发 PUT）；ArrowDown/ArrowUp 移动高亮，Escape、失焦或点击外部关闭；没有高亮时 Enter 仍走手输路径，尚未同步到本地的 label 照旧可以自由输入。候选接口失败时静默隐藏下拉，手输与保存不受影响；保存仍由「保存配置」提交完整集合。

## 8. 验证

- SQLite/MySQL 迁移：既有 workspace_id 全部回填，升级可重复检测，降级不删除公共事实。
- 同步：A label 同时配置两个空间时只写一条 bad_cases、写两组关联；B 只进一个；非法和无人配置分别计数；分页失败整页回滚；重试无重复。
- 配置：权限、精确匹配、完整替换、历史补齐、删除规则和事务回滚。
- 读侧：列表、Session、总览、额度、自进化对同一空间返回相同去重集合；配置变化不影响既有 run。
- UI：原型一致的导航/卡片/按钮、键盘添加、只读角色、空态、错误、原子保存反馈与窄屏。

