# 02 · 功能点拆分

> 本文回答：原型里到底有哪些功能、每个功能的数据是真是桩、它落在哪个域、对应哪个接口/表/组件。
> 前置：[01 总体架构](01-architecture.md)；下游：[03 前端架构](03-frontend-architecture.md) / [04 后端架构](04-backend-architecture.md) / [05 接口设计](05-api-design.md)。

## 1. 功能地图

先看一眼原型的关键截图（Session 4 张来自 `harness-evolution.html`，自进化 4 张来自 `evolution.html`，均在 [原型目录](../14-15-ui-prototype/)）：

**Session 错误查看**

| Agent 执行流图 | 错误详情与归因 |
|---|---|
| ![Agent 执行流图](../14-15-ui-prototype/screenshot-claude-code-execution-flow.png) | ![错误详情](../14-15-ui-prototype/screenshot-claude-code-errors.png) |

| 归因分析 | 问题卡与定位 |
|---|---|
| ![归因分析](../14-15-ui-prototype/screenshot-claude-code-attribution.png) | ![问题卡](../14-15-ui-prototype/screenshot-claude-code-problem.png) |

**自进化**

| 运行列表 | 启动向导（命中确认） |
|---|---|
| ![自进化运行列表](../14-15-ui-prototype/screenshot-evolution-list.png) | ![启动向导](../14-15-ui-prototype/screenshot-evolution-wizard.png) |

| 运行详情（第 5 步迭代） | 仅聚类结果 |
|---|---|
| ![运行详情](../14-15-ui-prototype/screenshot-evolution-detail.png) | ![仅聚类结果](../14-15-ui-prototype/screenshot-evolution-cluster.png) |

> F19 对象配置、F20 执行日志是新增功能，原型没有对应截图；功能点仍在 §2.2 定义。

```text
                         ┌───────────────────┐
                         │ Harness Evolution │
                         └─────────┬─────────┘
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
┌─ Session 错误查看 ──┐  ┌─ 自进化 ─────────────┐  ┌─ 横切能力 ──────────┐
│ F3 Session 列表     │  │ F10 运行列表         │  │ F1 顶部导览          │
│ F4 会话概览         │  │ F11 启动向导         │  │ F2 ID 体系与深链     │
│ F5 Agent 执行流图   │  │ F12 仅聚类结果       │  │ F9 轨迹接入与归一化  │
│ F6 会话内问题列表   │  │ F13 运行详情         │  │ F14 进度推送（SSE）  │
│ F8 错误详情与归因   │  │ F19 进化对象配置     │  │ F15 对象/模型清单    │
│                     │  │ F20 执行日志         │  │ F18 登录与鉴权       │
└─────────────────────┘  └──────────────────────┘  └──────────────────────┘
```

## 2. 功能点明细

图例：**真实性** = 真实（由同步/外部表驱动）/ 占位（fixtures 或占位算法）/ 混合（真实骨架 + 占位内容）；**阶段**沿用 [README](README.md) 的定位（S=会话查看，E=自进化，C=横切）。

### 2.1 Session 错误查看域

| ID | 功能 | 原型出处 | 真实性 | 依赖接口 | 依赖表 | 前端落点 |
|---|---|---|---|---|---|---|
| F3 | Session 列表：搜索（标题/仓库）、状态 chips（全部/完成/有失败）、排序（最新/用户轮次/消息/子 agent）、卡片密度条（失败/百消息、问题/百消息） | [浏览器页](../14-15-ui-prototype/harness-evolution.html) | 真实 | `GET /api/sessions` | `session_families`（聚合列） | `pages/sessions/SessionList.vue` |
| F4 | 会话概览：标题、meta、状态徽章、9 项统计条、CTA（打开错误详情） | 同上 | 真实 | `GET /api/sessions/{sid}` | `session_families` | `pages/sessions/SessionOverview.vue` |
| F5 | Agent 执行流图：主会话/子 agent/workflow 节点、节点链（skill/subagent/workflow 触发 + ×N message 间隔）、问题卡（`self` / `discovery` 两类锚定）、折叠组 | 同上 | **真实**：结构来自轨迹表，问题卡来自外部 `bad_cases` | `GET /api/sessions/{sid}/tree` | `agents`、`agent_events`、`bad_cases` | `components/agent-tree/*` |
| F6 | 会话内问题列表：bad_case 列表（reason 文案、状态、上报对象、metaData 事实）、定位联动、`badCaseId` 深链 | 同上 | 真实（外部写入，只读） | `GET /api/sessions/{sid}/bad-cases` | `bad_cases`、`bad_case_analysis` | `components/bad-cases/BadCaseList.vue` |
| ~~F7~~ | ~~时间线：用户轮次分组、类型过滤、消息卡、展开/折叠~~ **已裁撤（2026-10-22 决策：不做）**；`user_turns/messages/content_blocks` 表仍保留，仅用于列表/会话概览的统计聚合与后续诊断 | — | — | —（不提供读接口） | `user_turns/messages/content_blocks`（内部） | — |
| F8 | 错误详情与归因：左栏 bad_case 卡（5 种展示状态）、执行流按问题过滤、问题描述/归因分析双 Tab、结论横幅、根因对象、推导过程、非问题原因 | 同上 | 真实（`bad_cases` + 外部归因 `probe_reports`，只读） | `GET /api/bad-cases/{badCaseId}`、`/analysis`、`GET /api/probes/{probeId}` | `bad_cases`、`bad_case_analysis`、`probe_reports` | `pages/errors/*` |

### 2.2 自进化域

| ID | 功能 | 原型出处 | 真实性 | 依赖接口 | 依赖表 | 前端落点 |
|---|---|---|---|---|---|---|
| F10 | 运行列表：进行中（脉冲+进度条+阶段文案）/ 历史两组；卡片含根因对象 chip、时间窗、模型 chips、probe/簇统计、best vs 初始、已接纳数 | [自进化页](../14-15-ui-prototype/harness-evolution.html) | 真实（编排）+ 占位 patch/评测 | `GET /api/evolution/runs` | `evolution_runs`、`probe_clusters` | `pages/evolution/RunList.vue` |
| F11 | 启动向导：两步 Modal（根因对象/版本/时间段/模型 → 命中统计（session/报告/已分析/未分析）+ 属性分布 + 分页 probe 表（含模型列）），对象/版本/模型全部由后端接口加载，出口「仅聚类」「启动自进化」均返回 `202` 后跳转显示 preparing | 同上 | 真实（probe 查询）+ 占位聚类 | `GET /api/catalogs/targets`、`GET /api/evolution/targets/{id}/versions`、`GET /api/catalogs/models`、`POST /api/evolution/probes/query`、`POST /api/evolution/cluster-previews`、`POST /api/evolution/runs` | `evolution_targets`、`agents`、`session_families`、`probe_reports`、`evolution_runs` | `pages/evolution/LaunchWizard.vue` |
| F12 | 仅聚类结果页：`preparing` 准备态、输入概况（session/报告/已分析/未分析、时间窗、模型）、聚类列表（簇内 probe）、一键转完整自进化 | 同上 | 真实（占位聚类算法） | `POST /api/evolution/cluster-previews`、`GET /api/evolution/runs/{rid}/steps/clusters` | `probe_clusters`、`probe_cluster_probes` | `pages/evolution/ClusterPreview.vue` |
| F13 | 运行详情：`preparing/running/blocked` 状态、目标与输入 panel（已分析/未分析、最终用于进化的问题数、属性分布条、分支/base commit、eval/push 状态）、6 步 stepper、第 5 步自动逐轮 candidate → push → 评测 → 接纳/拒绝 → 下一轮、第 6 步终评；blocked 时按阶段重试 | 同上 | 编排/聚类/patch/commit/push 真实；评测走外部 gateway（V1 可 fake）；终评占位 | `GET /api/evolution/runs/{rid}`、`GET .../steps/{input|clusters|attribution|severity|iteration|final}`、`POST .../retry` | `evolution_targets/runs/evolution_rounds/finals`、`probe_clusters/probe_cluster_probes` | `pages/evolution/RunDetail.vue` + `pages/evolution/components/*` |
| F19 | 进化对象配置页：列表/新增/编辑/删除；字段 objectType/objectName/repoUrl/subDir/defaultRef/enabled；入口在向导选择器右侧齿轮 | 新增（2026-10-23） | 真实 | `GET/POST/PUT/DELETE /api/evolution/targets`、`GET .../{id}/versions` | `evolution_targets` | `pages/evolution/targets/*` |
| F20 | 执行日志与异常：准备/候选/push/eval/接纳/拒绝/下一轮/阻塞/重试事件，失败与中断记录、错误详情、增量拉取 | 新增（2026-10-23） | 真实 | `GET /api/evolution/runs/{rid}/events`、SSE `run.event/run.blocked/run.failed/run.interrupted` | `evolution_run_events`、`evolution_runs.error_*` | `pages/evolution/components/RunLogPanel.vue` |

> F11 不读前端常量：对象/版本来自 `evolution_targets` + 仓库 tag，模型来自归一化后的 `agents.model`；三者都通过后端接口加载。
>
> 原型 Step2 文案提到“未分析报告会先补归因再进入聚类”；当前设计不提供触发分析端点，未分析只计数、不进入 probe 表，归因由外部系统完成。若要求自动补归因，需要另加分析任务，不在 V1。

### 2.3 横切能力

| ID | 功能 | 原型出处 | 真实性 | 依赖接口 | 依赖表 | 前端落点 |
|---|---|---|---|---|---|---|
| F1 | 顶部导览：两大视图切换、品牌、ID 串联网提示 | 全局 | 真实 | — | — | `App.vue` / `TopNav.vue` |
| F2 | ID 体系：URL 直接用 `badCaseId` / `probeId` / `runId`（真实 ID），UI 显示截短 ID；深链到 session 错误详情并指定 tab | 全局 | 真实 | 随 bad-case / probe 返回 | `bad_cases`、`probe_reports` | `utils/badCaseId.ts` + 深链 |
| F9 | 轨迹接入与归一化：第三方脚本只写 `trajectory_payloads`（原始 JSONL）；本服务后台定时读取、归一化、幂等写入业务表；保留上游 pull | design.md §7 + SaaS 前提 | 真实 | `POST /api/acquisition/sync`、`POST /api/acquisition/pull`、`GET /api/acquisition/status` | `trajectory_payloads`（只读）、`source_records`、`sync_runs` + `session_families/agents/user_turns/messages/content_blocks/agent_events` | 顶栏状态角标（admin 可立即处理） |
| F14 | 进度推送：**页面级 SSE**，仅 `preparing/running` 的 run 订阅；ticket 绑定 topics 与 cursor、完成/阻塞即关闭；已完成任务和轨迹归一化都走普通 REST | — | 真实（机制） | `POST /api/events/ticket`、`GET /api/events` | `evolution_run_events` | `composables/useRunEvents.ts` |
| F15 | 对象/模型清单：可进化对象/版本（来自 `evolution_targets` 配置 + 远端仓库 tag）、模型 chips（来自归一化后的 `agents.model`） | 向导 | 真实（只读聚合） | `GET /api/catalogs/targets`、`GET /api/catalogs/models` | `evolution_targets`、`agents`、`session_families` | `composables/useTargets.ts` / `useCatalogs.ts` |
| F16 | ~~模拟推进：对运行中的 run 推进一步~~ **已取消（2026-10-23）**：改为后台自动逐轮推进，生产 UI 不再提供按钮 | 详情页按钮 | — | — | — | — |
| F17 | 基础壳：健康检查、全局错误处理、空态/加载态/失败态 | 各页面 | 真实 | `GET /api/health` | — | `App.vue` + 各页面三态 |
| F18 | 登录与鉴权：登录页、access/refresh token、401 自动刷新、路由守卫、SSE 一次性票据、顶栏用户区与退出 | SaaS 前提 | 真实 | `POST /api/auth/login`、`POST /api/auth/refresh`、`POST /api/auth/logout`、`GET /api/auth/me`、`POST /api/events/ticket` | `users` | `pages/login/*` + `stores/auth.ts` |

## 3. 功能点 → 数据来源矩阵（哪些是桩）

| 数据 | 原型里的来源 | 本方案来源 | 接入真实实现的位置 |
|---|---|---|---|
| 会话列表/会话概览/Agent 会话树结构 | `SESSIONS` / `TREE` 常量 | 读 `trajectory_payloads` → 归一化业务表；上游 pull 同管线 | 外部脚本写 payload；本服务归一化 |
| Agent 执行流图上的问题卡 | `SESSIONS.findings` + 生成逻辑 | 外部 `bad_cases`（只读） | 上游上报/归因系统 |
| 问题的文案与事实 | `lastDefs` / `skillDef` / `reportedDef` 模板 | `bad_cases.reason` + `meta_data` | 同上 |
| 归因结论/分类/根因对象/推导 | `ERROR_META` | 外部 `probe_reports` + `bad_case_analysis`（只读） | 上游归因系统 |
| 问题报告（R-） | `REPORTS` 常量 | **取消**：probe 即归因报告 | — |
| 自进化 runs / 簇 / patch / eval / commit / final | `RUNS` / `PATCH` 常量 | runs 与簇由本服务写；patch/eval/final 为占位 | 后续接真实执行器 |
| 进化对象/版本清单 | `OBJECTS` / `VERSIONS` | `evolution_targets` 配置（repoUrl + defaultRef + subDir；版本取远端 tag） | 配置页维护；后续接远端版本下载 |
| 模型清单 | `MODELS` | `SELECT DISTINCT model FROM agents`（归一化时写入；主/子 agent 可不同） | 随定时归一化数据更新 |

**演示数据要求**：开发/演示用 `fixtures/` 种子数据（原型 4 会话 + 若干 bad_case/probe），通过 `python -m app.cli seed` 写入真实表；**运行时没有 Stub Provider 分支**，UI 永远读真实表。见 [07 §2](07-backend-implementation.md)。

## 4. 阶段切分建议（供后续 milestone 讨论，不是最终排期）

| 阶段 | 目标 | 包含功能 | 验收信号 |
|---|---|---|---|
| A. 骨架与契约 | 前后端架子、OpenAPI 契约、外部表接入、健康检查、登录鉴权 | F17、F1、F2 基建、F18、数据接入与 fixtures | 登录后能拉到 health 与清单；未登录访问 API 返回 401；`openapi-typescript` 生成物无漂移 |
| B. 轨迹接入与归一化 | 读 `trajectory_payloads` 待处理记录 + 上游 pull + 会话两页 | F9、F3、F4、F5（结构） | 同一 payload 重复处理不产生重复；payload 变更/parser 升级只重放对应 agent；切 MySQL 后同一套用例通过 |
| C. 问题与归因 | bad_case 列表/详情、归因 tab（外部只读） | F5（问题卡）、F6、F8 | bad_case 与 probe 来自真实表；`badCaseId` 深链可用；5 种展示状态正确 |
| D. 自进化 | 运行列表、向导、对象配置、六步详情、执行日志（真实 workspace/candidate push、eval gateway、自动逐轮推进） | F10–F13、F15、F19、F20 | 配置页可维护；candidate 先 push 再评测，接纳 fast-forward、拒绝删 candidate；失败/阻塞可在日志看到并可重试 |
| E. 接真执行 | 换真实执行器（本地/CI）与真实上游来源 | 占位实现替换 | 前端零改动，仅换后端实现 |

> 阶段 A–D 是"能演示完整原型"的最小闭环；E 是占位实现的兑现。milestone 讨论时再把 A–D 拆到 M2/M3/M4 的 issue 里。

## 5. 每个功能点的验收口径（摘要）

- **F3**：四个 session 一屏放得下；搜索/筛选/排序都是纯前端状态 + 查询参数；空列表显示空态而不是空白。
- **F4**：9 项统计数字与后端聚合一致；密度分母 = `messages_count`（design.md §7 确定的口径），满格 3/百消息。
- **F5**：问题卡归属由后端 `anchor.agentId + anchor.eventIndex` 决定，不按"最后一个 agent"猜测；`self` 与 `discovery` 的挂载方向正确；子 agent 超过 8 个折叠。
- **F6**：bad_case 按 `createdAt` 升序；`badCaseId` 截短显示、tooltip 全量；点击新窗口打开对应 session 的对应问题；定位会滚动并高亮问题卡。
- **F7（裁撤）**：不做时间线页面。用户轮次/消息/内容块仍入库，用于列表/会话概览的统计（用户轮次、消息、工具失败、token）与后续诊断；不提供任何时间线读接口，Agent 执行流图上"打开时间线"入口一并移除。
- **F8**：5 种展示状态（未分析/非问题/模型/prompt/错误）；"全部错误"恢复完整执行流；选中单个错误时只保留该问题卡；归因 tab 顺序固定（结论 → 原因/分类与根因对象 → 描述 → 推导 → 来源 bad_case）。
- **F10–F13**：真实 probe 数据 + 占位聚类；stepper 未到达节点不可点；进度百分比与阶段文案由后端给出；run 有独立 workspace 与 `evo/{YYYYMMDD}-{run_id}` 分支；每个 candidate 先 push 临时 ref 再评测，接纳后 fast-forward run 分支、拒绝删除 candidate。
- **F19**：只有配置且启用的对象出现在向导；配置校验 repoUrl/defaultRef/subDir，非法值返回 422；删除被 run 引用的配置返回 409。
- **F20**：每个 run 的阶段、candidate、评测、推送都有 `evolution_run_events` 行；`failed/interrupted` 有错误摘要与脱敏详情；刷新后日志仍可查。
- **F14**：断线 3 秒内自动重连；重连后进度不倒退。
- **F9**：同一 `(root_session_id, agent_session_id)` + 相同 hash/parser_version 重复处理零副作用；payload 变化或 parser 升级仅重放对应 agent；单条失败不毁整批（进 `sync_runs.errors`）；定时与手动并发只产生一个 sync job（`sync_lock`）。
- **F18**：未登录访问任意页面跳登录页；access 过期自动 refresh 一次，refresh 失效回登录页；SSE 票据一次性、60 秒有效、绑定 topics。
- **F2**：所有深链在新窗口打开后能恢复到同样的选中状态（session + case + tab / run + step）。
