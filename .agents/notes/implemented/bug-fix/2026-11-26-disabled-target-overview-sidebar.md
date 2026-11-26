# Agent Note: 总览右栏保留已停用进化对象

Status: implemented

[English](2026-11-26-disabled-target-overview-sidebar.en.md) | 中文

## Problem

生产「总览 → 进化对象总览」只读 `enabled=true` 的配置：`TargetOverviewService._analyses()` 固定 `enabled_only=True`，`GET /overview/targets` 的 `summary/items/total` 也只覆盖启用对象。管理员停用一个对象后，配置从整个总览消失，页面既看不出它仍存在，也没有入口重新启用；用户确认停用对象应保留在右栏但继续不参与其它统计（GitHub #626）。

## Decision

- 契约 additive：`TargetOverviewListResponse` 增加 `disabled: [TargetOverviewDisabledItem]`，只含 `targetId/objectType/objectName/attributionSkillName/defaultRef`；`TargetOverviewItem` 与 `TargetOverviewSummary` 字段不变，生成类型由 `pnpm contract:generate` 产出。
- 服务端 `list_targets()` 额外读一次同空间 `enabled_only=False`，筛出 `enabled=false` 后按对象名、类型、id 稳定排序写入 `disabled`；该列表与分页无关，每页都返回空间全量。`trend`、`cases`、`detail` 与 `summary`、`items`、`total` 仍只走启用对象。
- Web 数据流让 `disabled` 与 `items` 保持两条通道：`TargetsOverview` 把 `disabled` 直接传给 `TargetSideList`，不并入 `targetItems`，因此筛选、趋势、分布、单对象选择器与潜在 bad case 列表天然看不到停用对象。
- `TargetSideList` 把启用行与停用行拼成同一分页序列（每页 5 条）：启用行之后追加虚线分组「已停用对象 · 仅展示，不参与统计」，停用行置灰、标注「已停用」、展示归因 Skill，并提供启用/编辑/移除。停用行没有选中按钮，不进入 `selected`。
- 启用动作复用既有 `useEvolutionTargets().updateTarget`：按对象当前配置组装 `EvolutionTargetWrite`（`enabled=true`，保留 `attributionPackageId`），走服务端正常的仓库/ref 校验；成功后失效总览并回到第 1 页，失败显示服务端错误，不做本地乐观切换。
- 测试覆盖 API `disabled` 与 `summary/total` 口径、组件分组顺序/徽标/不可选中/启用与编辑/移除事件、E2E 停用行可见、不进入选择器、点击启用后统计恢复。

## Alternatives considered

- **把停用对象并入 `items` 并加 `enabled` 字段**：拒绝。`items` 是 `evolvable` 排序和所有统计的唯一来源，并入后筛选、图表、详情选择器、潜在 bad case 列表都要逐个排除，任何漏改都会让停用对象重新进入统计。
- **新增 `GET /overview/targets/disabled` 端点**：拒绝。停用元数据与对象列表同一页面、同一权限、同一刷新节奏，独立端点只增加一次往返与一套缓存键；issue 也明确不新增端点。
- **前端直接把停用行拼进 `targetItems` 再过滤**：拒绝。会让「停用不参与统计」从服务端契约退化为前端碰巧正确，组件测试之外没有保护。
- **启用时只 PATCH `enabled` 字段**：拒绝。当前 API 只有整对象 `PUT`，新增部分更新会扩大契约与校验面；按现有配置组装完整写入即可复用既有校验和错误映射。
- **本地乐观地把行移回启用列表**：拒绝。启用需要服务端校验仓库/ref 并可能失败；乐观切换会在失败时显示错误统计，issue 要求失败只显示服务端错误。

## Consequences

- 总览右栏出现「已停用对象」分组；顶部 6 个统计、趋势、两块分布、单对象分析卡、筛选下拉与潜在 bad case 列表的数值和选项不变。
- 右栏分页总数包含停用对象，符合 issue 允许的口径；启用对象仍按 `evolvable` 降序、每页 5 个。
- `GET /overview/targets` 每次多一条同空间的停用对象查询；与启用对象的分析查询相互独立，停用对象不触发版本解析或匹配。
- 启用仍走完整的对象写入校验，仓库不可达或 ref 不存在时保持停用并显示服务端错误；对象配置页的表单字段与启停入口由 #628 负责，本 PR 未改。
- 停用对象只提供启用/编辑/移除，没有历史统计或详情下钻；`enabled=false` 对启动向导、绑定批次、归因与 run 的既有语义不变。
