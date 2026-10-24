# Harness Evolution 前后端整体设计方案

> 目标：把 [14-15-ui-prototype 原型](../14-15-ui-prototype/harness-evolution.html) 里的全部功能与 UI 效果，落成一套**可逐步实现、打桩位清晰、后续可快速接入真实实现**的前后端系统。
> 状态：**讨论稿** —— 等待 review，确认后再排 milestone / roadmap / issue。
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
| [09 Review 指南与待讨论问题](09-review-guide.md) | 原型→功能点→设计位置的追溯矩阵、Q1–Q5 开放问题、评审重点 | **review 时先看这篇** |
| [10 Milestone/Roadmap/Issue 重排草案（待确认）](10-roadmap-draft.md) | 设计确认后怎么排期：6 个 milestone、约 36 个 issue 草案、5 个待拍板问题 | 讨论排期时 |

## 系统一句话说明

Harness Evolution 是一个**面向 coding agent 的轨迹查看与问题诊断 SaaS 服务**：第三方脚本把有问题的 Claude Code 会话轨迹（主会话 + 子 agent 组成的 Agent 会话树）写入 MySQL 的 `trajectory_payloads`，本服务读取并归一化；也支持从"轨迹查询接口"按需 pull。归一化后供组织内登录用户在 Agent 执行流图上查看主/子 agent 的执行过程、对暴露的问题做归因分析，再按 skill / agent 聚合问题报告，驱动"聚类 → 归因 → 打 patch → 评测接纳 → 终评"的自进化闭环。时间线页面（原型 B 页）在 2026-10-22 评审中决定不做，完整时间线由外部平台承担；本服务只保留用户输入锚点，见 [02 §2.1](02-features.md)。

```text
轨迹输入：上游查询接口 / trajectory_payloads（脚本写入）
                    │
                    ▼
┌─ apps/api · Python + FastAPI 模块化单体 ──────────────────────┐
│ acquisition ──► sessions / bad_cases / probes / evolution     │
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
│ Session 错误查看：浏览器 / 错误详情                           │
│ 自进化：运行列表 / 详情 / 向导 / 对象配置                     │
└───────────────────────────────────────────────────────────────┘
```

## 已确认的顶层决策（2026-10-22 与维护者讨论拍板）

| # | 决策点 | 结论 | 影响 |
|---|---|---|---|
| D1 | 前端框架 | **Vue 3 + Vite** | 原型 Agent 执行流图从 React Flow 迁到 [Vue Flow](https://vueflow.dev/)（同为 xyflow 官方出品）；约 600 行几何布局是纯 TS，结构迁移；`×N` 改为 message 口径 |
| D2 | 后端落地 | **新建 `apps/api`（Python + FastAPI）**，替换现有 `apps/server`（Fastify+TS 壳） | 现有 TS 后端只有健康检查，无沉没成本；仓库文档中"Fastify"表述需同步更新 |
| D3 | 契约事实源 | **FastAPI OpenAPI 为唯一事实源**，`openapi-typescript` 生成 TS 类型存入 `packages/contracts` | 保留仓库"contracts 是共享协议唯一来源"的约定，但内容改为生成物 + CI 防漂移校验 |
| D4 | 演示数据与外部数据（2026-10-22 修订） | **问题/归因数据来自外部只读表；演示数据用 `fixtures/` + `seed` 灌入真实表**，运行时没有 Stub Provider 分支 | API 契约全真；UI 永远读真实表；上游/外部表就绪后无需切换前端或契约。详见 [01 §5](01-architecture.md) |
| D5 | 部署形态（2026-10-22 修订） | **SaaS 服务**：多用户、远程访问、MySQL 主库；不再是本地单机工具 | 引入鉴权、用户体系与远程部署；原先"预留服务化"的接缝全部兑现 |
| D6 | 自进化边界（2026-10-23 修订） | **V1 真实修改 skill/agent 文件、candidate commit、push 临时 ref 供评测，接纳后 fast-forward run 分支**；聚类与 patch 内容、评测分数为占位 | candidate 先 push 到 `.../candidate/r{n}` 再评测；接纳 amend + ff，拒绝删 candidate；run 分支只含已接纳 commit；push 失败 blocked |
| D7 | 进度推送 | **页面级 SSE**：仅 `preparing/running` 的 run 订阅；ticket 绑定 topics 与 cursor，完成/阻塞即关闭；轨迹归一化走 REST 轮询 | EventSource 不能带头，用一次性票据；已完成任务不建 SSE |
| D8 | 范围裁剪（2026-10-22） | **时间线页面（原型 B 页）不做，完整时间线由外部平台承担** | 本服务只保留 `user_turns` 用户输入锚点，消息/内容块不落库；移除时间线路由、接口、组件与对应里程碑 issue。见 [02 §2.1](02-features.md) |
| D9 | 数据库可替换（2026-10-22） | **MySQL 是默认主库**；存储层提供统一 `Database` 接口，SQLite 适配器保留用于测试与本地开发 | 表结构按跨库通用类型设计；生产连 MySQL，测试用 SQLite，业务代码与前端零改动。见 [04 §4](04-backend-architecture.md) |
| D10 | 租户模型（2026-10-22） | **单组织共享**：登录即可见全部数据 | 核心表只记 `created_by`，不做行级隔离；后续如需隔离再加 `owner_id` 过滤 |
| D11 | 鉴权（2026-10-22） | **自建账号 + JWT**（users 表 + argon2 + access/refresh token） | 不依赖外部 SSO；初始管理员由 env 播种；后续用户由管理员创建 |
| D12 | 轨迹来源（2026-10-23 修订） | **第三方脚本只写 `trajectory_payloads`（每 agent 一行原始 JSONL）；本服务后台定时读取+归一化，不采集/扫描外部源表**；上游接口 pull 保留，拉到后写同一张 payload 表 | payload 只存一份；`source_records` 只是处理索引；定时 + 单飞锁避免并发；幂等靠 `(root_session_id, agent_id)` + hash + `parser_version` |
| D13 | 进化对象配置（2026-10-23） | **只有配置且启用的 skill/agent 才能自进化**；配置含 repoUrl/subDir/defaultRef/enabled；入口在向导选择器右侧齿轮 → 配置页 | 从远端仓库拉取并按分支/tag 取基线；版本列表来自远端 tag；模型清单来自归一化后的 `agents.model` |
| D14 | 自进化 git 流程（2026-10-23） | **candidate commit → push 临时 candidate ref → 评测 → 接纳 amend + fast-forward run 分支 / 拒绝删 candidate；push 是评测前置条件** | run 分支只含已接纳 commit，评测用 `.../candidate/r{n}`；push 失败 run 进入 blocked，3 次立即 + 1/5/15min 退避，`/retry` 恢复 |
| D15 | 执行过程与异常（2026-10-23） | **所有阶段/候选/评测/推送事件与异常写 `evolution_run_events`**；Web UI 读库展示，SSE 只做实时通知 | 刷新/重进不丢执行历史；失败与中断可定位；异常脱敏后入库 |

## Review 前必看：6 个待确认项

设计已按 SaaS 前提重写，以下 6 项需要你拍板后才会进入 roadmap/issue 与实现（详细选项见 [09 §2](09-review-guide.md)）：

| # | 待确认 | 当前建议 |
|---|---|---|
| 1 | UI 控件库与主题 | Element Plus 只做控件，结构自研；首版只做亮色 |
| 2 | 「模拟推进」按钮 | **已定**：生产 UI 删除；后台自动逐轮推进 |
| 3 | 「查看原始 JSON」overlay | 首版不做，后续按诊断证据需求再加 |
| 4 | 用户管理界面范围 | 首版只做 API + 顶栏用户区，不做管理页 |
| 5 | 轨迹归一化触发方式 | 后台定时（默认 60s）+ 单飞锁；手动仅 admin 立即处理 |
| 6 | 上游轨迹查询契约（[05 §10](05-api-design.md)） | 按"轨迹包 + 窗口列举"设计；如果你知道上游实际 API 形态，告诉我再调整 |

## 数据边界与演示数据（全局最重要的设计约束）

- **轨迹**：第三方脚本/上游 pull → `trajectory_payloads`（每 agent 一行原始 JSONL）→ `service/acquisition` 归一化 → 业务表。
- **问题与归因**：外部系统写 `bad_cases` / `bad_case_analysis` / `probe_reports`，本服务**只读**。
- **自进化**：本服务写 `evolution_targets` / `evolution_runs` / `evolution_run_events` / `probe_clusters` / `evolution_rounds` / `evolution_finals`；**真实修改配置仓库副本、candidate commit、push 临时 candidate ref 供评测，接纳后 fast-forward run 分支**（candidate 先 push 再评测；拒绝删 candidate，run 分支不变）。
- **执行过程**：阶段、候选、评测、推送、异常全部落 `evolution_run_events`；前端通过 `GET /runs/{rid}/events` 读取，SSE 只做实时通知。
- **演示数据**：`fixtures/` + `python -m app.cli seed`，仅开发/演示灌入真实表；运行时无 stub 分支。
- **V1 占位**：聚类用"按 attribute_type 分半"的占位算法；patch 内容追加占位小节但**真实落盘/commit**；评测/终评为占位分数。

机制细节见 [01 §5](01-architecture.md) 与 [06](06-database-design.md)。

## 与仓库现状的关系

- 本方案对应 roadmap 的 **M2（平台骨架 + 登录鉴权）+ M3（轨迹接入与归一化）+ M4（问题与归因，外部表只读）+ M5（自进化，占位聚类/执行）+ M6（接真）** 的目标态设计；当前 M1（纯前端原型）已由 [plans/14-15-ui-prototype](../14-15-ui-prototype/) 完成。
- `apps/web` 现有 React 壳（3 个文件）由 Vue 3 应用替换；`apps/server` 由 `apps/api` 替换；`packages/contracts` 保留但改为存放 OpenAPI 生成物。
- 本次 SaaS 化修订后，`docs/architecture.md` 中"当前只做 Codex / 本机 rollout 扫描 / Fastify"等表述将不再成立，需按本设计同步（确认后执行）。
- 文档确认后的后续动作：重排 roadmap / milestone / issue（`.agents/flow/`），把 `docs/architecture.md` 的技术栈表述同步为新架构，再逐 issue 实现。
- 原型截图直接复用为各文档插图（相对路径 `../14-15-ui-prototype/screenshot-*.png`），设计稿中的 UI 描述以 [harness-evolution.html](../14-15-ui-prototype/harness-evolution.html) 为最终验收基准。
