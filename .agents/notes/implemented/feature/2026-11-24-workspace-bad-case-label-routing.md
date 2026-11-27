# Agent Note: 公共 badcase 按 label 划分空间的可关联事实与统一读边界

Status: implemented

[English](2026-11-24-workspace-bad-case-label-routing.en.md) | 中文

## Problem

生产 badcase 统一上报到公共仓库，平台定期拉取后需要按 `items[].meta_data.label` 把同一条公共 badcase 同时提供给多个空间，并让列表、Session、统计和自进化使用同一空间边界。旧的 `bad_cases.workspace_id` 是单值字段：既表达归属又表达可见性，无法表达"一条公共 badcase 因同一 label 属于多个空间"；把记录复制成多行又会撞 `bad_case_id` 全局主键。上游 `/bad-cases` 没有 label 筛选参数，分配只能在平台侧做。

## Decision

- `bad_cases` 保留单份公共事实（`bad_case_id` 全局主键），可见性从 `bad_cases.workspace_id` 移到 `workspace_bad_cases` 关联表，主键 `(workspace_id, bad_case_id, assignment_source)`。
- `assignment_source` 三态：`legacy_owner`（迁移把既有 `workspace_id` 回填）、`direct_ingest`（空间凭据直接上报）、`catalog_label`（公共目录 label 命中）。迁移按 `bad_cases.origin` 区分存量：`report` 行回填 `direct_ingest`，`catalog` 行回填 `legacy_owner`，并把存量 catalog 行的 `meta_data.label` 按同一契约投影到 `catalog_label`、`catalog_synced` 置真，回填可重复执行。同一空间与 case 可同时有直接上报与 label 两种关联，读取用 `DISTINCT` 去重。
- 空间接受的 label 存 `workspace_bad_case_labels(workspace_id, label)`；label 是 1–128 字符、无首尾空白、区分大小写的精确字符串，一个 label 可配置给多个空间。PUT 全量替换的 `items` 必填，`[]` 才表示显式清空。
- `bad_cases.catalog_label` 是同步时对 `meta_data.label` 验证后写入的可空投影列（直接上报固定 `NULL`），不是第二事实源：统计与重建只查该列，不在 SQL 里解析 JSON，保持 SQLite/MySQL 一致并可走索引。
- 目录同步的单页事务按序执行：upsert 事实 → 删本页 ID 的 `legacy_owner` 与旧 `catalog_label` 关联 → 按规则 `INSERT…SELECT` 重建 → 更新游标与 assigned/unassigned/invalid 计数；任何一步失败整页回滚、游标不前进。
- 保存 label 配置在一个事务里锁定空间、全量替换规则、只删该空间的 `catalog_label` 关联，再从 `bad_cases.catalog_label JOIN workspace_bad_case_labels` 重建历史关联；新增规则补齐历史、删除规则撤销实时可见性。
- 所有空间读路径（Session 列表与树、问题列表、总览、额度、潜在 badcase 与自进化取数）统一经 `WorkspaceReadScope.case_condition()` 走关联；`bad_cases.workspace_id` 只保留直接上报归属（ID 冲突检测与 owner 展示）。归因进度聚合按请求空间匹配 `probe_reports.workspace_id`，不跟 `bad_cases.workspace_id`，label 共享 case 的报告只计入产出它的空间。
- `GET /api/workspaces/{wid}/bad-case-labels/suggestions` 是只读词表：聚集 `bad_cases.catalog_label` 的非空值及其出现次数，`q` 为最长 128 的可选区分大小写前缀，`limit` 取 1–50 默认 20，空 `q` 返回 Top N，按计数降序、同数按字典序，`%`/`_` 按字面量转义；viewer 可读，不按当前空间规则收窄，也不读其他空间的规则集合。空间管理输入框用它做候选下拉：聚焦空输入展示 Top N，输入经 200ms 防抖按前缀过滤，点击或方向键高亮后 Enter 只把候选加入草稿，已配置 label 不进候选，接口失败静默降级为手输，保存仍是完整集合替换。

## Alternatives considered

- **把公共 case 复制到每个匹配空间**：拒绝。撞 `bad_case_id` 全局主键，且失去单份事实，label 变更要批量删改多行。
- **读路径沿用 `bad_cases.workspace_id`，或用 `workspace_id OR 关联` 兜底**：拒绝。目录同步再次触达同 ID 时移除 `legacy_owner` 后，旧默认空间会因兜底继续看到公共数据，可见性收口失效。
- **label 过滤在 SQL 里解析 `meta_data` JSON**：拒绝。SQLite/MySQL 的 JSON 函数与索引行为不一致，且无法覆盖缺失/非法 label 的计数口径。
- **物化 label 字典或回写公共仓库**：拒绝。不建立第二事实源，也不改动上游数据生产方式。
- **追溯修改已创建的自进化运行输入**：拒绝。已持久化候选、报告与运行快照不反查实时关联，配置变化只影响后续预览和新运行。

## Consequences

- 每次空间化读多一次关联 `EXISTS`/`IN` 子查询；`workspace_bad_case_labels`、`workspace_bad_cases` 与 `bad_cases.catalog_label` 列是新的事实面，迁移按 `origin` 回填 `direct_ingest`/`legacy_owner` 并把存量 catalog 标签投影到 `catalog_label`。
- `bad_cases.workspace_id` 成为仅属直接上报的兼容字段，移除需要单独的兼容窗口。
- 公共目录分配可使空间 `used > quota`：直接上报继续按额度拒绝，管理页提示调整额度或移除 label；`used` 统一按关联去重计数。
- 配置保存只在整个事务提交后返回，读取不会观察到规则与关联不一致的中间态；同步与重算重试幂等。
- 测试 fixture 直接写 `bad_cases.workspace_id` 的场景须按迁移语义回填关联（`report` → `direct_ingest`，其余 → `legacy_owner`），否则空间化读为空。
