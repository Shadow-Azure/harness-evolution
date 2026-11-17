# Agent Note: 四步启动向导与启动条件快照

Status: implemented

[English](2026-11-17-four-step-launch-wizard.en.md) | 中文

## Problem

V1 向导只有「筛选问题报告 → 确认命中」两步，命中源是旧 probe 报告，无法表达 V2 的「对象版本出现在哪些 Session → 哪些 bad case 属于潜在集合 → 归因缓存能复用多少」。如果把潜在判定、版本关联或缓存复用放到前端重算，向导、错误详情与运行详情会各自维护一套口径，展示数字与真正启动的 run 不一致。反过来，若四步预览各自重新执行归因，第 4 步就会在用户确认前产生写操作，违背「预览只读」。

## Decision

- `LaunchWizard.vue` 重写为四步状态机：选择范围 → Session 关联 → 潜在 bad case → 归因预览与启动。第 2–4 步只消费服务端 `preview/sessions`、`preview/potential`、`preview/attribution` 的 summary 与分页行，前端不重算潜在集合、不拼接命中原因。
- 第 1 步是唯一的条件编辑面。对象/版本/时间段/策略任一变化都会清空后续预览并回到第 1 步；第 2、3 步的分页只重发当前端点的 `page`，不重跑前一阶段。
- 策略只有两个入口语义：`{preset:"default"}` 或 `{preset:"custom", includeSelfReport, includeAfterObject, sameObjectOnly}`。custom 至少启用一条匹配规则，本地拦截与后端 `422 POLICY_INVALID` 使用同一规则；策略只在第 1 步可改，避免第 3 步就地改变潜在集合。
- `409 NO_ASSOCIATED_SESSIONS` 用 `details.summary` 渲染第 2 步的五段空态计数并禁用前进；`409 NO_POTENTIAL_MATCHED` 在第 3 步渲染空态并禁用前进。空态不伪造 200 空页。
- 第 4 步缓存开关默认开，切换会重新请求只读归因预览；四个数字直接来自 `{potential,reused,fresh,nonTargetKnown}`，UI 不把四个数字相加。两个出口沿用 `cluster_only` 与 `full` 两种 `202` 受理语义。
- 启动请求把当前策略与缓存开关随条件一起提交：`policy` 由 `resolve_policy` 校验并展开成显式开关，`cacheEnabled` 与 `potential_policy` 一起冻结到 `evolution_runs` 快照。这样第 4 步展示的潜在集与缓存策略就是新 run 实际使用的策略，而不是等到 prepare 阶段再读请求方当前值。
- `focusCaseId` 通过 `?case=` / 组件 prop 进入：读取空间内 bad case 后预选对象与版本，并显示只读提示；它不改变潜在判定口径，也不自动扩大时间段。错误详情页的按钮由 m11-02 接入，本切片只提供入口能力。
- 第 2 步表格只有「Session / 对象出现 / 对象触发点 / bad case 数」四列，不展示潜在数：该端点契约只做关联，潜在数属于第 3 步，避免同一页出现两套口径。

## Alternatives considered

- **前端用 bad case 列表重算潜在集合**：会与 `PotentialMatcher` 的 self/after_object、坐标顺序和 sameObjectOnly 语义漂移；拒绝，所有计数以服务端 summary 为准。
- **四步拆成四个独立弹窗/路由**：条件会跨页面复制，修改条件后的失效逻辑更难保证；拒绝，保持单弹窗、单 ref 状态机。
- **第 4 步开关只改展示文案，启动时不带缓存策略**：run 快照会与预览不一致（预览显示复用、run 却重算）；拒绝，把 `policy`/`cacheEnabled` 纳入启动 body 与 run 快照。
- **第 3 步允许就地改策略**：会悄悄改变潜在集合，却保留旧分页；拒绝，策略修改统一回第 1 步重新预览。
- **空态按通用 200 空页处理**：会丢掉五个 Session 分区计数，用户无法解释为什么没有关联；拒绝，保留 409 并用 details 解释。
- **把 focus case 的时间也自动填成同一天**：会把潜在窗口缩到单日，改变判定口径；拒绝，只预选对象/版本。

## Consequences

- 启动 body 的 `policy`/`cacheEnabled` 是 m10-04 七步 prepare 的输入契约；本切片先完成契约与快照落库，真正消费快照的七步管线仍由 m10-04 接管。在 m10-04 合入前，旧 prepare 仍按 probe 命中运行，第 4 步的潜在数不会直接变成旧管线的输入。
- `preview/attribution` 只读：不写 `probe_reports`、`bad_case_analysis` 或候选；第 4 步的 `fresh` 是「潜在 − 复用」的推算值，不是已生成的归因数。
- 缓存键包含解析后的 `targetRevision`、策略版本与归因引擎；同一对象不同 revision 不会互相复用，历史非该对象计数只是参考值。
- E2E 使用真实 API + SQLite + fixture corpus，并补写 skill 事件的 `object_version`/`object_revision`/`triggered_at` 与 target `default_ref`；fixture 事件本身不携带对象版本，这是测试夹具的边界。
- 启动后的异步 prepare 可能失败（例如测试 remote 不可达），向导只对 `202` 受理负责；运行详情与 blocked/retry 由后续切片展示。
