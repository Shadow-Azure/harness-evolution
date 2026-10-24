# 09 · Review 指南与已决问题

> 本文是给维护者 review 用的"对照清单 + 决策清单"：先核对原型有没有被完整覆盖，再按 §2 结论进入排期。
> 前置：[README](README.md)（决策记录）· [02 功能点拆分](02-features.md)（功能明细）。

## 1. 原型 → 功能点 → 设计位置的追溯矩阵

用法：对着原型从左到右看一遍，任何一行"设计位置"为空或对不上，就是需要补的窟窿。

### 1.1 全局

| 原型元素 / 交互 | 功能点 | 设计位置 |
|---|---|---|
| 顶部导览：品牌、两大视图切换、ID 串联网提示 | F1 | [03 §6](03-frontend-architecture.md) · [08 §1](08-frontend-implementation.md) |
| 真实 ID（`badCaseId` / `probeId` / `runId`）与点击深链（新窗口、指定 tab） | F2 | [05 §5](05-api-design.md) · [08 §7](08-frontend-implementation.md) |
| 健康检查、空态/加载/失败三态 | F17 | [05 §4.1](05-api-design.md) · [08 §13](08-frontend-implementation.md) |
| 登录页（用户名/密码、错误提示、登录跳转） | F18 | [05 §4.1](05-api-design.md)（auth 端点）· [08 §4](08-frontend-implementation.md) |
| 强制改密页（首登改密、成功后换 token 并放行） | F18 | [05 §4.1](05-api-design.md)（`change-password`）· [08 §4.1](08-frontend-implementation.md) · [07 §8.2](07-backend-implementation.md) |
| 顶栏用户区：演示数据角标、轨迹处理状态、当前用户与退出 | F18 / F9 | [08 §4.2](08-frontend-implementation.md) |
| 轨迹处理状态（`GET /acquisition/status`）与后台定时 | F9 | [05 §4.8](05-api-design.md) · [08 §4.3](08-frontend-implementation.md) |

### 1.2 Session 错误查看

| 原型元素 / 交互 | 功能点 | 设计位置 |
|---|---|---|
| 左栏：标题 + 会话数量 | F3 | [02 §2.1](02-features.md) · [08 §5](08-frontend-implementation.md) |
| 搜索框（标题/仓库，输入即筛） | F3 | [05 §4.2](05-api-design.md)（`q`） |
| 状态 chips：全部 / 完成 / 有失败 | F3 | [05 §4.2](05-api-design.md)（`status`） |
| 排序下拉：最新 / 用户轮次 / 消息 / 子 agent | F3 | [05 §4.2](05-api-design.md)（`sort`） |
| 会话卡：状态点、标题、时间、repo chip、时长、工具数、子 agent 数 | F3 | [05 §3.1](05-api-design.md)（`SessionListItem`） |
| 会话卡：5 项统计（用户轮次/消息/工具失败/Skill/问题） | F3 | [05 §3.1](05-api-design.md)（`stats`） |
| 会话卡：失败密度条 + 问题密度条（每百消息，3 满格） | F3 | [06 §7.3](06-database-design.md)（口径）· [08 §5.3](08-frontend-implementation.md)（绘制） |
| 右栏头：状态点 + 标题 + meta（开始时间/repo/时长/模型/状态徽章） | F4 | [05 §3.1](05-api-design.md) |
| 右栏 CTA：打开错误详情（原「打开时间线」随 F7 裁撤移除） | F4 | [08 §1](08-frontend-implementation.md) · [08 §6](08-frontend-implementation.md) |
| 9 项统计条（用户轮次/消息/工具/失败/子 agent/Skill/Token/失败密度/问题密度） | F4 | [05 §3.1](05-api-design.md) |
| Agent 执行流图：图例（主会话/子 agent/Workflow/Skill 触发/Subagent 触发/×N message 间隔/问题） | F5 | [03 §8.3](03-frontend-architecture.md) · [08 §3](08-frontend-implementation.md) |
| Agent 执行流图：主会话与子 agent 节点、节点链、Skill/Subagent/Workflow 触发药丸 | F5 | [05 §3.2](05-api-design.md)（`events`）· [08 §3.2](08-frontend-implementation.md) |
| Agent 执行流图：×N message 间隔节点（`messagesCount` + `messageOffset`） | F5 | [08 §3.2](08-frontend-implementation.md)（`chainOf`） |
| Agent 执行流图：问题卡（`#badCaseId 截短 + reason`）`self` / `discovery` 两类锚定规则 | F5 | [08 §3.2](08-frontend-implementation.md)（锚定规则） |
| Agent 执行流图：>8 子 agent 折叠为"N 个子 agent · 点击展开" | F5 | [08 §3.2](08-frontend-implementation.md)（折叠规则） |
| Agent 执行流图：滚轮缩放 / 拖拽平移 / 右下角 Controls / 自适应 | F5 | [08 §3.3](08-frontend-implementation.md) |
| 问题列表：`badCaseId` 截短、reason、状态、上报对象、metaData 事实 chips | F6 | [05 §3.4](05-api-design.md) · [08 §3.4](08-frontend-implementation.md) |
| 问题列表：点击「定位 ↗」→ 画布滚动 + 高亮 + 聚焦 | F6 | [08 §3.4](08-frontend-implementation.md) |
| 问题列表：`badCaseId` 点击新窗口打开问题描述 tab | F2/F6 | [05 §5](05-api-design.md) |
| 时间线页（面包屑/过滤 chips/用户轮次头/提问卡/消息卡/展开折叠/跳转） | ~~F7~~ | **已裁撤（2026-10-22）**：不实现，理由与替代见 [02 §2.1](02-features.md) · [08 §6](08-frontend-implementation.md) |
| 错误详情左栏：错误数量、session 标题/id、返回 Session | F8 | [08 §7](08-frontend-implementation.md) |
| 错误详情左栏："全部错误" + bad_case 卡（ID/状态 chip/reason/上报对象） | F8 | [05 §3.4](05-api-design.md) · [08 §7.2](08-frontend-implementation.md) |
| 错误详情右栏头：meta、返回 Session（原「打开时间线」移除） | F8 | [08 §7.1](08-frontend-implementation.md) |
| 执行流面板：未选时显示全部问题，选中时只留该问题卡 | F8 | [08 §7.2](08-frontend-implementation.md) |
| 双 Tab：问题描述 / 归因分析 | F8 | [08 §7.3](08-frontend-implementation.md) |
| 问题描述：badCaseId、reason、状态 chip、metaData facts、上报对象 | F8 | [05 §3.4](05-api-design.md) |
| 归因：结论横幅（问题/非问题/未分析） | F8 | [05 §3.4](05-api-design.md)（`analysis.status`）· [08 §7.3](08-frontend-implementation.md) |
| 归因：根因对象、问题分类、问题描述、分析推导过程（Markdown） | F8 | [05 §3.4](05-api-design.md)（`ProbeReport`） |
| 归因：非问题原因 | F8 | 同上（`analysis.result.reason`） |
| 归因：未分析空态 | F8 | 同上（`unanalyzed` 占位） |
| 不实现：卡片「查看原始 JSON」overlay（原属时间线卡片） | — | **首版裁剪**，见 §2 问题 Q3 |

### 1.3 自进化

| 原型元素 / 交互 | 功能点 | 设计位置 |
|---|---|---|
| 列表：标题、说明、启动按钮 | F10 | [08 §8](08-frontend-implementation.md) |
| 列表："正在执行"组（脉冲 + 数量）与"历史记录"组 | F10 | [05 §4.10](05-api-design.md)（`running/history`） |
| run 卡：根因对象 chip、时间窗、模型 chips、probe/簇统计 | F10 | [05 §3.5](05-api-design.md)（`RunCard`） |
| run 卡：进行中进度条 + 阶段文案 + 百分比 | F10 | [05 §3.5](05-api-design.md)（`progress`） |
| run 卡：已完成 best vs 初始 + Δ + 接纳 patch 数 + 有效/无收益徽章 | F10 | 同上（`final`） |
| 列表空态："当前没有正在执行的自进化" | F10 | [08 §8](08-frontend-implementation.md) |
| 向导：两步指示器 | F11 | [08 §9.1](08-frontend-implementation.md) |
| 向导 step1：对象类型分段控件、名称/版本级联、时间段、模型多选 | F11 | [05 §4.11](05-api-design.md) · [05 §4.13](05-api-design.md) · [08 §9.2](08-frontend-implementation.md) |
| 向导 step1：选择器右侧齿轮 → 进化对象配置页 | F19 | [05 §4.11](05-api-design.md) · [08 §9.2](08-frontend-implementation.md) · [08 §9.5](08-frontend-implementation.md) |
| 配置页：列表/新增/编辑/删除，repoUrl/subDir/defaultRef/enabled | F19 | [05 §4.11](05-api-design.md) · [08 §9.5](08-frontend-implementation.md) |
| 向导 step1 → step2：查询命中 | F11 | [05 §4.9](05-api-design.md) |
| 向导 step2：条件摘要 + 修改条件 | F11 | [08 §9.3](08-frontend-implementation.md) |
| 向导 step2：3 项统计 + 属性分布条 + 图例 | F11 | [05 §4.9](05-api-design.md)（`summary/byAttributeType`） |
| 向导 step2：probe 表（probe ID/会话/根因对象/属性/来源 bad_case） | F11 | [05 §4.9](05-api-design.md)（`items`） |
| 向导 step2：分页（每页 8 条） | F11 | [05 §7](05-api-design.md) |
| 向导 step2：两个出口「仅聚类」「启动自进化」 | F11 | [05 §4.9–4.10](05-api-design.md) · [08 §9.3](08-frontend-implementation.md) |
| 向导 step2：未关联 session 的行不渲染链接 | F11 | [08 §9.3](08-frontend-implementation.md) |
| 详情：返回列表、标题、状态徽章、preparing/blocked | F13 | [05 §4.10](05-api-design.md)（`status/blockedStage`） |
| 详情：目标与输入 panel（8 项 kv + 类型分布条 + 图例） | F13 | [05 §3.5](05-api-design.md)（`stats/byAttributeType`） |
| 详情：工作区信息（分支/base commit/路径） | F13 | [05 §3.5](05-api-design.md)（`workspace`）· [08 §10.2](08-frontend-implementation.md) |
| 详情：6 步 stepper、当前查看标注、点击规则（已完成/进行中可点） | F13 | [05 §3.5](05-api-design.md)（`steps[].status/clickable`）· [08 §10.2](08-frontend-implementation.md) |
| 第 1 步：probe 筛选表（含归属簇） | F13 | [05 §3.6](05-api-design.md)（step 0） |
| 第 2 步：聚类卡 + 簇内 probe 列表 | F13 | [05 §3.6](05-api-design.md)（step 1） |
| 第 3 步：归因确认（根因对象/属性/描述/推导） | F13 | [05 §3.6](05-api-design.md)（step 2） |
| 第 4 步：严重程度排序表（顺序/类型/probe 数/严重度） | F13 | [05 §3.6](05-api-design.md)（step 3） |
| 第 5 步：迭代卡（patch → push → eval → 决策：接纳 ff / 拒绝删 candidate） | F13 | [05 §3.6](05-api-design.md)（step 4）· [07 §5.6](07-backend-implementation.md) |
| 第 6 步：verdict 横幅、修改点清单、指标对比表 | F13 | [05 §3.6](05-api-design.md)（step 5） |
| 第 6 步：分支名、push 状态、blocked 阶段与重试 | F13 | [05 §4.10](05-api-design.md)（`workspace/pushStatus`）· [08 §10.2](08-frontend-implementation.md) |
| 执行日志：准备/候选/push/eval/阻塞/重试事件时间线、异常详情 | F20 | [05 §4.15](05-api-design.md) · [08 §10.4](08-frontend-implementation.md) |
| 失败/中断：状态徽章、错误摘要、刷新后仍可查 | F20 | [06 §5.7](06-database-design.md) · [08 §10.2](08-frontend-implementation.md) |
| 仅聚类页：banner、输入概况、聚类列表、一键转完整自进化 | F12 | [05 §4.12](05-api-design.md) · [08 §11](08-frontend-implementation.md) |
| 进度实时更新（SSE） | F14 | [04 §7.3](04-backend-architecture.md) · [05 §4.14](05-api-design.md) · [08 §2.6](08-frontend-implementation.md) |
## 2. 已决设计问题（按原讨论顺序）

> 以下结论于 2026-10-24 固化；实现时以本节结论和链接章节为准。

### Q1. UI 控件库与主题（已定）

- **背景**：参考报告用 Element Plus；原型是纯自研亮色样式（CSS 变量令牌）。
- **已定（2026-10-24）**：Element Plus 只用于表单控件、弹窗、日期、分页与消息，布局和业务组件自研，保证与原型视觉一致。
- **范围**：首版只做亮色；令牌结构保留暗色扩展位。

### Q2. 自动逐轮推进（已定）

- **已定（2026-10-23）**：生产 UI 删除按钮；`POST /advance` 端点删除；后台自动逐轮推进。
- 由 `eval_poller` + `blocked_sweeper` + `/retry` 处理评测等待与失败恢复。

### Q3. 「查看原始 JSON」overlay（已定不纳入）

- 原型：overlay 组件挂在时间线卡片上（"查看原始载荷"），时间线裁撤后该入口不复存在。
- **已定（2026-10-24）**：首版不纳入。后续若做诊断证据查看，按 `(sessionId, agentId, lineNo)` 从 `trajectory_payloads.payload` 回读（见 [06 §3.0](06-database-design.md)）；不恢复消息/内容块明细表。

### Q4. 用户管理界面范围（已定）

- 现状：自建账号 + JWT（D11），单组织共享，初始管理员 env 播种，用户由 admin 创建。
- **已定（2026-10-24）**：首版只做 API（`GET/POST /users`）+ 顶栏显示当前用户与退出；管理操作先用 API/脚本完成，不进 UI。
- **边界**：V1 不提供停用/恢复用户 API；`is_active` 继续作为登录闸门字段保留，未来恢复停用管理时再补写路径。

### Q5. 轨迹归一化的触发方式（已定）

- 现状：后台 scheduler 默认每 60s 处理 pending；`POST /api/acquisition/sync` 仅 admin/运维立即处理，幂等返回已有 jobId。
- **已定（2026-10-24）**：定时 + 单飞锁；无 pending 跳过；手动仅 admin。

### Q6. 上游轨迹查询契约（已定）

- **已定（2026-10-24）**：[05 §10](05-api-design.md) 是本服务定义的客户端契约，`HttpApiSource` 与 mock 契约联调按该契约实现；不把它解释为真实上游已承诺该契约。
- **边界**：真实上游就绪时以其实现为准；主版本不兼容时先评审并适配，不静默放宽校验。

## 3. 评审重点（高风险设计，建议逐条确认）

| # | 风险点 | 为什么重要 | 设计中的对策 |
|---|---|---|---|
| R1 | React Flow → Vue Flow 迁移 | Agent 执行流图是原型最复杂的部分；Handle/边 API 有差异 | 布局几何纯 TS 迁移；先做 `demo-nested` 最小树验收；`×N` 改为 message 口径（[03 §8.3](03-frontend-architecture.md)） |
| R2 | 外部问题/归因表契约 | 字段漂移会让整个错误页与自进化失效 | 只读表 + 查询层防御（缺字段降级、日志告警）；fixtures 与真实表同构；上游表变更需评审（[06 §4](06-database-design.md)） |
| R3 | SSE 与 REST 的一致性 | 事件与查询结果可能短暂不一致 | 事件只做通知/追加；run 事件从 `evolution_run_events` 回放，REST 是事实源（[04 §7.3](04-backend-architecture.md)） |
| R4 | 六步状态机 | 前端推算会与后端漂移 | 状态由后端算，`status/clickable` 直出（[07 §5.1](07-backend-implementation.md)） |
| R5 | 契约生成物 | 手工同步必漂移 | OpenAPI 快照 + `contract:check` CI（[05 §6](05-api-design.md)） |
| R6 | 深链 ID 校验 | 前缀猜 session 会串会话 | 解析后用 `sessionId` 校验，不匹配报 409（[05 §5](05-api-design.md)） |
| R7 | 归一化幂等与重放 | 重复处理会脏数据 | `(root_session_id, agent_id)` + payload hash + `parser_version`；事务内先删后写（[07 §2.2](07-backend-implementation.md)） |
| R8 | SQLite / MySQL 行为差异 | 本地绿、切库红 | 双库 CI（`-m mysql`）+ SQL 纪律（不用方言语法、索引列 VARCHAR、JSON 不查 SQL），见 [06 §1.1](06-database-design.md) |
| R9 | 上游查询接口不存在 / 契约漂移 | pull 来源一直空着或解析失败 | 契约先行（[05 §10](05-api-design.md)）；脚本 payload 先跑通；上游响应头声明版本，不兼容拒绝启动 |
| R10 | `trajectory_payloads` 结构与预期不一致 | 归一化整批失败 | 单条隔离 + 表名可配 + 结构校验前置（[07 §2.6](07-backend-implementation.md)） |
| R11 | 占位聚类/占位 patch 被误当真实结论 | 演示后被当成产品能力 | UI 明确标注"占位"；占位逻辑集中在 `service/evolution`，有单测锁定行为 |
| R12 | git 操作失败/仓库配置错误 | run 卡住或提交丢失 | 保存配置与启动 run 双重校验；candidate 先 commit、接纳 amend + fast-forward、拒绝删 candidate（run 分支不 reset）；失败标 `failed` 并保留工作区；push 前校验分支命名与 base |
| R13 | push 失败（凭据/远端冲突/网络） | 评测平台拿不到 candidate，流程阻塞 | candidate 推临时 ref；3 次立即 + 1/5/15min 退避；仍失败 run blocked，保留 candidate，`/retry` 恢复；run 分支不回滚 |
| R14 | 执行异常只存在日志/内存，刷新即丢 | 无法定位失败原因 | 所有过程与异常写 `evolution_run_events`；job 边界统一捕获；启动扫描残留 `running` 记 `interrupted` |
| R15 | 异常详情泄露密钥/环境/密码 | 安全风险 | `error.detail` 脱敏（HE_*、token、URL 凭据、`password`/`password_hash`）并截断 8KB；接口只返回脱敏内容；密码与哈希不写任何 payload 列；commit message 同样脱敏且只含 ID（[06 §3.8](06-database-design.md) · [07 §5.8](07-backend-implementation.md)） |
| R16 | 定时与手动同时触发同步 | 重复处理/并发写同一 session | `sync_lock` 单飞 + TTL；手动幂等返回已有 `jobId`；`job_runs` 仅一个活跃 sync |
| R17 | 评测接口长时间不返回/超时 | 单 worker 被占、页面误以为卡死 | `eval_poller` 每 5min 轮询、`next_poll_at` 落库、超时置 `blocked(eval)`；`/retry` 重新提交 |

## 4. 确认后的下一步

```text
你 review 本文档集
  ▼
按 §2 的 Q1–Q6 结论进入排期
  ▼
重排 roadmap / milestone / issue
  ▼
更新 .agents/flow/ 并跑 verify:flow
  ▼
按 issue 顺序开始实现
```

- milestone 讨论会基于 [02 §4 阶段切分建议](02-features.md) 与现有 roadmap 的 M2/M3/M4 进行重组（例如把"骨架与契约"单独成阶段）；具体草案见 [10 路线图重排草案](10-roadmap-draft.md)。
- 每个里程碑会给出验收标准（对应本文 §1 的追溯矩阵），不写"实现完成"这种无法验证的描述。

## 5. Review checklist（快速勾选用）

- [ ] 功能覆盖：§1 矩阵里没有"未覆盖"的功能（除 Q3 的 overlay）
- [ ] 数据边界：轨迹（本服务写）/ 问题归因（外部只读）/ 自进化（本服务写）三类归属认可
- [ ] 演示数据：`fixtures` + seed，运行时不打桩的方式认可
- [ ] 技术选型：Vue 3 / Vue Flow / Element Plus / FastAPI / SQLAlchemy 全部认可
- [ ] 契约：OpenAPI 生成 + CI 校验方案认可
- [ ] 数据库：MySQL 主库 + SQLite 测试的 `Database` 双实现与切换方式认可
- [ ] 部署与身份：SaaS 单实例 + 自建账号 JWT + 单组织共享认可
- [ ] 轨迹来源：契约先行（05 §10）+ 第三方写 `trajectory_payloads`、本服务只归一化的方式认可
- [ ] 范围：时间线页面裁撤（F7 不做）、归因阶段不聚类（自进化阶段才聚类）确认
- [ ] 自进化：对象配置（repoUrl/defaultRef/子目录）、candidate 先 push 临时 ref 再评测、接纳 amend+fast-forward、拒绝删 candidate、push 失败 blocked + 1/5/15min 退避
- [ ] 执行日志：过程/异常落库、事件 API、前端日志与失败/中断展示认可
- [ ] SSE：`preparing/running` 页面级订阅、ticket 绑定 topics/cursor、blocked/终态关闭、断线从 DB 回放
- [ ] 自进化执行：准备异步、自动逐轮、评测前 push、candidate ref、blocked + 3 次立即 + 1/5/15min 退避、`/retry`
- [ ] 前端结构：API 按域拆、页面专属组件 co-locate、IconRenderer、node/jsdom 测试配置认可
- [x] 设计问题：Q1–Q6 已有结论
