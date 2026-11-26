# Harness Evolution 前后端整体设计方案

> 目标：以 [V1 原型](../14-15-ui-prototype/harness-evolution.html) 为基线，把 [V2 原型](../ui-prototype-v2/harness-evolution.html) 的工作空间、总览、上报、多归因与七步自进化落成一套**可逐步实现、打桩位清晰、后续可快速接入真实实现**的前后端系统。
> 状态：V1 已实现；**V2 关键设计决策已确认（2026-11-11）**；M7–M12 的 milestone / roadmap / issue 已落在 `.agents/flow/`，当前排期以 [roadmap](../../.agents/flow/roadmap.md) 为准，10 号文档为历史草案。
>
> 术语：用户可见文案统一为 **Agent 会话树**（对象）、**会话概览**（摘要）、**Agent 执行流图**（图）。数据模型统一为 `session_families` / `agents` / `user_turns` / `agent_events`；消息与内容块只在解析期用于统计，不落库；前端组件为 `agent-tree/`、`AgentTree.vue`、`SessionOverview.vue`，API 类型 `SessionTree` 保留。

## 这套文档怎么读

```text
01 总体架构（系统在怎么分层）
  ▼
02 功能点拆分（到底要做哪些功能）
  ├──► 03 前端架构（用什么搭、怎么组织）──┐
  ├──► 04 后端架构（用什么搭、怎么组织）──┼──► 05 接口设计（前后端怎么对话）
  │                                        └──► 06 数据库设计（数据怎么存）
  │                                                    │
  │                    ┌───────────────────────────────┴──────────────┐
  │                    ▼                                              ▼
  │            07 后端实现设计                                  08 前端实现设计
  │                    └───────────────────────────────┬──────────────┘
  └────────────────────────────────────────────────────┴──► 09 Review 指南
```

| 文档 | 回答的问题 | 适合谁先看 |
|---|---|---|
| [01 总体架构设计](01-architecture.md) | 系统边界、分层、数据流、打桩机制、部署形态 | 所有人 |
| [02 功能点拆分](02-features.md) | 原型里每个功能是什么、数据是真是桩、归哪个域 | 所有人 |
| [03 前端架构与组件选型](03-frontend-architecture.md) | Vue 3 技术栈、分层、目录、组件体系、状态管理 | 写前端前 |
| [04 后端架构与组件选型](04-backend-architecture.md) | FastAPI 技术栈、模块化单体、外部表接入、任务与 SSE | 写后端前 |
| [05 后端接口设计](05-api-design.md) | REST 端点、请求/响应模型、SSE 事件、错误模型、深链契约 | 写任何一端前 |
| [06 数据库表结构设计](06-database-design.md) | ER 图、逐表字段、索引、迁移策略 | 写后端前 |
| [07 后端接口的实现设计](07-backend-implementation.md) | 每个功能域的路由/服务/数据访问/任务怎么落地 | 写后端时 |
| [08 前端的实现设计](08-frontend-implementation.md) | 每个页面的组件树、数据流、交互与打桩接入点 | 写前端时 |
| [09 Review 指南与已决问题](09-review-guide.md) | 原型→功能点→设计位置的追溯矩阵、Q1–Q6 决策记录、评审重点 | **review 时先看这篇** |
| [10 Milestone/Roadmap/Issue 历史草案（superseded）](10-roadmap-draft.md) | V1→V2 排期的历史讨论稿；当前排期见 [`.agents/flow/roadmap.md`](../../.agents/flow/roadmap.md) | 查历史决策时 |
| [11 bad_cases 根会话轨迹定时同步](11-bad-case-session-sync.md) | 自动补齐策略、外部查询服务契约、状态表、重叠处理与前端统计 | 做 m6-15 前 |
| [12 bad_cases 目录数据定时同步](12-bad-case-catalog-sync.md) | 上游分页查询契约、游标翻页、upsert、状态表与前端统计 | 做 m6-16 前 |
| [13 根会话 ID 的展示与检索](13-root-session-id.md) | 错误页两处展示、会话搜索匹配 `id`、契约与性能边界 | 做 m6-18 前 |
| [15 V1/V2 差距与前端差异](15-v1-v2-gap-analysis.md) | 当前实现相对 V1、V2 相对 V1 的功能与界面差异，以及 V2 改动地图 | 做 V2 前 |
| [16 bad case 同步源工厂化](16-bad-case-sync-source-factory.md) | global 源线的父类 / 子类 / 工厂、`HE_BAD_CASE_SYNC_PROVIDER` 开关矩阵、已上报 bad case 的写者归属、`_sync_root` 单循环收敛，以及目录 / root 两条数据流的逐步 JSON 对照 | 做同步源工厂化实现 issue 前（#548） |
| [17 公共 badcase 按 label 划分工作空间](17-workspace-bad-case-label-routing.md) | 公共目录单份事实、空间 label 规则、多对多关联、历史重算、统一读边界与管理页签 | 做 #582 前 |
| [18 同仓多成员进化对象](18-multi-member-evolution-target.md) | 一条配置 + 成员表的领域模型、共享与成员边界、迁移回填、API / 后端流程 / 前端交互与兼容策略 | 做 m28-01 前 |

## 系统一句话说明

Harness Evolution 是一个**面向 coding agent 的轨迹查看与问题诊断 SaaS 服务**：第三方脚本把有问题的 Claude Code 会话轨迹（主会话 + 子 agent 组成的 Agent 会话树）写入 MySQL 的 `trajectory_payloads`，本服务读取并归一化；也支持从"轨迹查询接口"按需 pull。V2 起 bad case 经**工作空间上报接口**（`POST /api/workspaces/{wid}/bad-cases`，额度管控）进入，归一化后供组织内登录用户在 Agent 执行流图上查看主/子 agent 的执行过程；**归因由自进化流程按「对象 · 版本」生成**，一个 bad case 可有多条归因，再按 skill / agent 聚合驱动"关联 → 潜在筛选 → 归因 → 聚类 → 打 patch → 评测接纳 → 终评"的自进化闭环。时间线页面（原型 B 页）在 2026-10-22 评审中决定不做，完整时间线由外部平台承担；本服务只保留用户输入锚点，见 [02 §2.1](02-features.md)。

```text
轨迹输入：上游查询接口 / trajectory_payloads（脚本写入）
                    │
                    ▼
┌─ apps/api · Python + FastAPI 模块化单体 ──────────────────────┐
│ acquisition ──► sessions / bad_cases / workspaces / evolution  │
│ identity（登录 · JWT · 票据）   events（SSE 事件总线）        │
└───────────────────────────┬───────────────────────────────────┘
                            ▼
                ┌──────────────────────────────┐
                │ MySQL 8（主库）              │
                │ 业务表 + payload 表 + users  │
                └──────────────┬───────────────┘
                               │ REST（OpenAPI 契约）+ SSE
                               ▼
┌─ apps/web · Vue 3 + Vite SPA（登录态） ───────────────────────┐
│ 工作空间总览：bad case / 进化对象                              │
│ Session 错误查看：浏览器 / 错误详情 / 多归因                   │
│ 自进化：运行列表 / 详情 / 向导 / 对象配置                      │
│ 空间管理：空间 / 成员 / 上报 / 鉴权接入                        │
└───────────────────────────────────────────────────────────────┘
```

## 已确认的顶层决策（2026-10-22 与维护者讨论拍板；2026-10-24 补齐 review 结论）

| # | 决策点 | 结论 | 影响 |
|---|---|---|---|
| D1 | 前端框架 | **Vue 3 + Vite** | 原型 Agent 执行流图从 React Flow 迁到 [Vue Flow](https://vueflow.dev/)（同为 xyflow 官方出品）；约 600 行几何布局是纯 TS，结构迁移；`×N` 改为 message 口径 |
| D2 | 后端落地 | **新建 `apps/api`（Python + FastAPI）**，替换现有 `apps/server`（Fastify+TS 壳） | 现有 TS 后端只有健康检查，无沉没成本；仓库文档中"Fastify"表述需同步更新 |
| D3 | 契约事实源 | **FastAPI OpenAPI 为唯一事实源**，`openapi-typescript` 生成 TS 类型存入 `packages/contracts` | 保留仓库"contracts 是共享协议唯一来源"的约定，但内容改为生成物 + CI 防漂移校验 |
| D4 | 演示数据与外部数据（2026-10-22；V2 由 D21/D23 修订） | **V1 问题数据来自外部同步，V2 主通道改为空间上报；演示数据用 `fixtures/` + `seed` 灌入真实表**，运行时没有 Stub Provider 分支 | API 契约全真；UI 永远读真实表；V2 的 bad case 写入与归因生成都在本服务边界内。详见 [01 §5](01-architecture.md) |
| D5 | 部署形态（2026-10-22 修订） | **SaaS 服务**：多用户、远程访问、MySQL 主库；不再是本地单机工具 | 引入鉴权、用户体系与远程部署；原先"预留服务化"的接缝全部兑现 |
| D6 | 自进化边界（2026-10-23 修订） | **V1 真实修改 skill/agent 文件、candidate commit、push 临时 ref 供评测，接纳后 fast-forward run 分支**；聚类与 patch 内容、评测分数为占位 | candidate 先 push 到 `.../candidate/r{n}` 再评测；接纳 amend + ff，拒绝删 candidate；run 分支只含已接纳 commit；push 失败 blocked |
| D7 | 进度推送 | **页面级 SSE**：仅 `preparing/running` 的 run 订阅；ticket 绑定 topics 与 cursor，完成/阻塞即关闭；轨迹归一化走 REST 轮询 | EventSource 不能带头，用一次性票据；已完成任务不建 SSE |
| D8 | 范围裁剪（2026-10-22） | **时间线页面（原型 B 页）不做，完整时间线由外部平台承担** | 本服务只保留 `user_turns` 用户输入锚点，消息/内容块不落库；移除时间线路由、接口、组件与对应里程碑 issue。见 [02 §2.1](02-features.md) |
| D9 | 数据库可替换（2026-10-22） | **MySQL 是默认主库**；存储层提供统一 `Database` 接口，SQLite 适配器保留用于测试与本地开发 | 表结构按跨库通用类型设计；生产连 MySQL，测试用 SQLite，业务代码与前端零改动。见 [04 §4](04-backend-architecture.md) |
| D10 | 租户模型（2026-10-22，V2 由 D21 取代） | **V1 单组织共享；V2 改为工作空间级隔离** | V2 以 `workspace_id + workspace_members` 收口 bad case 与权限；轨迹表仍全局共享，通过 bad case 投影空间 Session |
| D11 | 鉴权（2026-10-22） | **自建账号 + JWT**（users 表 + argon2 + access/refresh token） | 不依赖外部 SSO；初始管理员由 env 播种；后续用户由管理员创建 |
| D12 | 轨迹来源（2026-10-24 修订） | **第三方脚本只写 `trajectory_payloads`（每 agent 一行原始 JSONL，带 `runtime_key`）；本服务后台定时（默认 60s）+ 单飞锁读取并归一化，admin 可手动立即处理，不采集/扫描外部源表**；上游接口 pull 保留，拉到后写同一张 payload 表 | payload 只存一份；`source_records` 只是处理索引；定时 + 单飞锁避免并发；手动 sync 复用运行中的任务；幂等靠 `(runtime_key, root_session_id, agent_id)` + hash + per-runtime `parser_version` |
| D13 | 进化对象配置（2026-10-23；V2 按空间） | **只有当前空间配置且启用的 skill/agent 才能自进化**；配置含 repoUrl/subDir/defaultRef/enabled；入口在向导提示文案内的「配置页」链接 → 配置页 | 从远端仓库拉取并按分支/tag 取基线；版本列表来自远端 tag；V2 向导不再做模型多选 |
| D14 | 自进化 git 流程（2026-10-23） | **candidate commit → push 临时 candidate ref → 评测 → 接纳 amend + fast-forward run 分支 / 拒绝删 candidate；push 是评测前置条件** | run 分支只含已接纳 commit，评测用 `.../candidate/r{n}`；push 失败 run 进入 blocked，3 次立即 + 1/5/15min 退避，`/retry` 恢复 |
| D15 | 执行过程与异常（2026-10-23） | **所有阶段/候选/评测/推送事件与异常写 `evolution_run_events`**；Web UI 读库展示，SSE 只做实时通知 | 刷新/重进不丢执行历史；失败与中断可定位；异常脱敏后入库 |

| D16 | UI 控件与主题（2026-10-24） | **Element Plus 只做表单控件、弹窗、日期、分页与消息；布局和业务组件自研；首版只做亮色，令牌结构保留暗色扩展位** | 视觉以原型设计令牌为准；Element Plus 只做少量变量映射，避免整站组件化导致视觉偏离原型。见 [03 §2](03-frontend-architecture.md) · [03 §9](03-frontend-architecture.md) |
| D17 | 原始 JSON 查看（2026-10-24） | **首版不提供「查看原始 JSON」overlay 或独立入口** | 时间线裁撤后没有消费入口；后续诊断功能可按 `(sessionId, agentId, lineNo)` 回读 payload，不恢复消息/内容块明细表。见 [06 §3.0](06-database-design.md) |
| D18 | 用户管理（2026-10-24） | **首版只提供 admin 的 `GET/POST /api/users` 和顶栏用户区；不做管理页，也不提供停用/恢复用户 API** | 管理操作先走 API/脚本；`is_active` 继续作为登录闸门字段保留，未来恢复停用管理时再补写路径。见 [05 §4.1](05-api-design.md) · [08 §4.2](08-frontend-implementation.md) |
| D19 | 上游轨迹查询契约（2026-10-24） | **[05 §10](05-api-design.md) 是本服务定义的客户端契约，用于 `HttpApiSource` 和 mock 契约联调；不表示真实上游已承诺该契约** | 上游就绪前继续用 `trajectory_payloads` 和 fixtures；真实上游接入时以其实现为准，主版本不兼容先评审适配，不静默放宽校验。 |
| D20 | 测试工程 ID（2026-10-31） | **验证集/测试集测试工程 ID 挂在 `evolution_targets`，创建 run 时快照到 `evolution_runs`；必填在 API/表单层，不调用外部平台校验存在性** | 历史 target/run 为空串；本切片不改 run API、详情页与评测 gateway。见 [14](14-target-project-ids.md) |
| D21 | 多工作空间（2026-11-11，V2；2026-11-24 修订） | **工作空间是 bad case 的可见性与权限单元**：空间直接上报与公共目录 label 分配统一投影到 `workspace_bad_cases`；同一公共 badcase 可属于多个空间，空间 Session 集合 = 关联 badcase 涉及的根会话投影，轨迹表不加空间列；evolution_targets / evolution_runs / evolution_run_events 保留 `workspace_id` | 全局管理员唯一（禁建 admin、可自任空间管理员）；空间角色 `space_admin/member/viewer` 服务端收口。见 [17](17-workspace-bad-case-label-routing.md) |
| D22 | 鉴权接入预留（2026-11-11，V2） | **身份栈不变（JWT + refresh cookie），鉴权接入收敛为 `AuthProvider` 协议 + 会话桥 + `GET /api/auth/callback` 占位**；新增 `GET /api/auth/session` 返回 user + workspaces；不开放注册，SSO 按 sub 匹配（email 不参与匹配）不自动建号 | 接入 Cookie/SSO 只改 provider/桥/callback 三处，业务与前端契约不变。见 [07 §8.2.1](07-backend-implementation.md) · [05 §4.16](05-api-design.md) |
| D23 | 对象绑定归因（2026-11-11，V2；2026-11-23 修订） | **每个进化对象绑定一个空间归因 Skill；Session 关联按对象类型和名称的出现，`targetRevision` 只固定原文、报告和缓存范围**；后台按绑定批次逐 Badcase 产出 V2 报告；向导按对象·版本取最新完成报告，或单次换 Skill 重算，然后聚类 | `probe_id` 继续作为 `attributionId`；报告保留来源 Skill、执行清单与绑定批次。`versionUnresolved` 仅为历史兼容字段。见 [02 对象绑定归因](02-features.md#对象绑定归因) · [05 §4.11/§4.20](05-api-design.md) · [06 §4.2.2/§5.1/§7.5](06-database-design.md) · [07 §5.13–5.14](07-backend-implementation.md) |
| D24 | 多 AI agent 轨迹（2026-11-16，V2；2026-11-20 修订） | **`runtime_key`（AI agent 类型）与 `source_type`（接入通道）分离，`runtime_key` 是身份/存储键；parser 由 `can_parse` 按轨迹选型并由 `TraceParserFactory.for_trace` 唯一实例化；parser 以会话为生命周期，构造时接收同 root 全部 payload；`parser_version` 按 runtime 解释**。新增 runtime 只新增子类并实现 `can_parse`/record/meta/会话链接；未知/歧义选型 fail fast，不回退 Claude | 公共 session 编排不因新增 runtime 修改；payload、source cursor、Session 和 API 都带 `runtime_key`。见 [07 §2.6](07-backend-implementation.md) · [06 §3.0.1](06-database-design.md) |
| D25 | 执行流双视图（2026-11-16，V2） | **默认小窗口 lane DAG，结构树保留为切换视图**；bar=日志行区间、`A1/A1.1` 深度、跨 lane 重叠=并发、全部 lane 展开、缩放/平移；选中 case 保留全部分支并高亮，不过滤；时间线不恢复 | 替代旧 Vue Flow 节点树/`>8` 折叠/按问题过滤。见 [03 §8.3](03-frontend-architecture.md) · [08 §3](08-frontend-implementation.md) |

## Review 前必看：结论状态

原 6 个 review 问题已固化：模拟推进见 D6，轨迹归一化触发见 D12，其余四项见 D16–D19。唯一外部边界是 [05 §10](05-api-design.md) 只是我方客户端契约；V2 排期已由 M7–M12 的 flow 树承接，不再以 10 号草案为准。

## 数据边界与演示数据（全局最重要的设计约束）

- **轨迹**：第三方脚本/上游 pull → `trajectory_payloads`（每 agent 一行原始 JSONL）→ `service/acquisition` 归一化 → 业务表。
- **问题与归因**：bad case 主通道是空间上报接口（[05 §4.17](05-api-design.md)，目录同步默认停用）；归因由自进化 run 写 `bad_case_analysis` 与 `probe_reports`（[06 §4.2](06-database-design.md) · [07 §5.13](07-backend-implementation.md)）；一 case 多归因由关联表表达，`probe_id` 继续作为稳定归因 ID。
- **自进化**：本服务写 `evolution_targets` / `evolution_runs` / `evolution_run_events` / `evolution_run_candidates` / `probe_clusters` / `evolution_rounds` / `evolution_finals`；**真实修改配置仓库副本、candidate commit、push 临时 candidate ref 供评测，接纳后 fast-forward run 分支**（candidate 先 push 再评测；拒绝删 candidate，run 分支不变）。
- **执行过程**：阶段、候选、评测、推送、异常全部落 `evolution_run_events`；前端通过 `GET /runs/{rid}/events` 读取，SSE 只做实时通知。
- **演示数据**：`fixtures/` + `python -m app.cli seed`，仅开发/演示灌入真实表；运行时无 stub 分支。
- **V1 占位**：patch 内容追加占位小节但**真实落盘/commit**；评测/终评为占位分数；聚类已由确定性词法算法替换，算法版本/阈值随 run 事件落库。

机制细节见 [01 §5](01-architecture.md) 与 [06](06-database-design.md)。

## 与仓库现状的关系

- 本方案对应 roadmap 的 **M2（平台骨架 + 登录鉴权）+ M3（轨迹接入与归一化）+ M4（问题与归因）+ M5（自进化，占位聚类/执行）+ M6（接真）** 的目标态设计；M7–M12 是 V2 的工作空间、证据、归因与 lane DAG 交付段，当前状态见 `.agents/flow/roadmap.md`。
- **V2 目标态**（2026-11-11 起）：多用户鉴权接入 + 多工作空间 + 总览 + 归因进自进化，按域并入 01–08：空间与鉴权见 [01 §4.4](01-architecture.md) · [05 §3.7/§4.16–§4.17](05-api-design.md) · [06 §3.10–3.12](06-database-design.md) · [07 §5.15/§8.2.1](07-backend-implementation.md) · [08 §4.2](08-frontend-implementation.md)；总览与 Session 列表见 [05 §3.10/§4.18](05-api-design.md) · [06 §7.5](06-database-design.md) · [08 §5.2.1/§6](08-frontend-implementation.md)；归因与七步流程见 [05 §3.6.2/§4.19–§4.20](05-api-design.md) · [06 §4.2/§5.8–5.10/§7.5](06-database-design.md) · [07 §5.11–5.14](07-backend-implementation.md) · [08 §7/§9/§10](08-frontend-implementation.md)；多 runtime parser 见 [07 §2.6](07-backend-implementation.md) · [06 §3.0.1](06-database-design.md)；lane DAG 见 [08 §3](08-frontend-implementation.md) · [03 §8.3](03-frontend-architecture.md)。原型基线为 [plans/ui-prototype-v2](../ui-prototype-v2/)；D10（单组织共享）与 D6/D13/D14 中与 probe 输入相关的表述以 D21–D25 为准修订；当前实现与两代原型的差距见 [15](15-v1-v2-gap-analysis.md)。
- 当前仓库已使用 `apps/web` Vue 3 + `apps/api` FastAPI + `packages/contracts` OpenAPI 生成物；V2 设计直接在当前实现上增量演进。
- V2 设计已按 D21–D25 同步到 `docs/architecture.md`；兼容面、V3 触发与机械退役清单见 [docs/compatibility.md](../../docs/compatibility.md)。
- 文档确认后的后续动作：M7–M12 已排入 `.agents/flow/`，按 issue 实现；本 PR 只更新设计与流程草案，`flow:sync` 在 review 后执行。
- V1 截图继续作为既有页面基线；V2 新增页面与交互以 [V2 harness-evolution.html](../ui-prototype-v2/harness-evolution.html) 和 [design-v2.md](../ui-prototype-v2/design-v2.md) 为验收基准。
