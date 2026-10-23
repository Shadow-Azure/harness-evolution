# 10 · Milestone / Roadmap / Issue 重排草案（待确认）

> **状态：讨论稿。** 本文不写入 `.agents/flow/`，不触发 `flow:sync`；等 [09 的 Q1–Q5](09-review-guide.md) 与本文 §5 的路线图问题都有结论后，再用 `pnpm flow:new-issue` 正式生成三件套并更新 roadmap。
> 目的：把"设计确认之后怎么排期"提前摆到桌面上，避免确认当天从零开始讨论。
> 范围前提（2026-10-22 多轮评审）：① 时间线页面（原型 B 页）裁撤；② 产品定位为 **SaaS 服务**（自建账号 + JWT、单组织共享、MySQL 主库）；③ 轨迹输入为"第三方脚本写入的 `trajectory_payloads` + 契约先行的上游 pull"，本服务只做归一化；问题/归因数据来自外部只读表；④ 演示数据用 `fixtures` seed，不做运行时打桩。

## 1. 先对齐现状与漂移

当前 `.agents/flow/roadmap.md` 的 M2–M4 写于数据源切换之前，存在三处需要修订的表述：

| 现有表述 | 问题 | 建议 |
|---|---|---|
| M2 "流式解析 JSONL…按 `parent_thread_id` 组装 session family…64 个 rollout" | 这是 Codex 术语；[design.md §7](../14-15-ui-prototype/design.md) 已切换为 Claude Code（`~/.claude/projects`，子转录靠 `toolUseId`） | 重写 M2（或新 M3）为 Claude Code 口径 |
| M2 "SQLite migration、repository 与 session/family/ingest/timeline API" | 没有提到"前端从 React 重建为 Vue 3"、"后端换成 FastAPI"与"登录鉴权"这三项平台级工作量 | 把平台骨架单独成阶段，否则 M2 一个 milestone 同时压四件事 |
| M3/M4 的验收写"至少一条真实问题走完诊断→提案→评测" | 与"外部归因只读 + 自进化占位"的 V1 边界冲突 | 拆成"外部数据接入 + 自进化占位"与"接真执行"两个阶段 |

## 2. 推荐路线图（6 个 milestone）

```text
M1 原型（已完成）
  ▼
M2 平台骨架与契约（Vue 3 + FastAPI + 鉴权 + 外部表接入）
  ▼
M3 轨迹接入与归一化（payload 读取 · 归一化 · 会话两页）
  ▼
M4 问题与归因（外部只读，UI 完整）
  ▼
M5 自进化闭环（占位执行，UI 完整）
  ▼
M6 接真实现（执行器 + 真实来源）
```

| id | 标题 | 状态 | 一句话目标 | 出口验收 |
|---|---|---|---|---|
| m1 | 前端体验原型（已完成，保持不动） | done | 4 个真实会话验证信息架构 | 原型 HTML 可演示（现状） |
| m2 | 平台骨架与契约 | planned | Vue 3 前端骨架 + FastAPI 后端骨架 + OpenAPI 契约 + 登录鉴权 + 外部表接入跑通 | `pnpm dev` 起前后端；登录后 `/api/health` 正常；未登录 401；`contract:check` 通过 |
| m3 | 轨迹接入与归一化 | planned | 读 `trajectory_payloads` + 上游 pull + 归一化入库（MySQL）+ 会话两页（列表/摘要）+ 家族树结构 | 同一 payload 重复处理不重复；结构异常按条隔离；切 MySQL 后同一套 API 与测试通过 |
| m4 | 问题与归因（外部只读） | planned | bad_case 列表/详情、归因 tab、家族树问题卡 | 5 种展示状态正确；badCaseId 深链可用；外部表字段缺失可降级 |
| m5 | 自进化闭环（占位聚类/评测） | planned | 对象配置、运行列表、启动向导、六步详情、workspace/candidate commit、执行日志 | 每个 candidate 有 commit；接纳 amend、拒绝 reset；失败/中断可在日志看到；进度经 SSE 更新 |
| m6 | 接真实现 | planned | 接真实执行器与上游来源：真实 PayloadSource/HttpApiSource、聚类升级、patch/评测执行 | 至少一条真实问题走完"payload → 归一化 → 聚类 → patch → 评测接纳或拒绝"；前端零改动 |

### 2.1 为什么这样拆

- **m2 单独成阶段**：前端要从 React 重建为 Vue 3，后端要从 Fastify 换成 FastAPI，还要加登录鉴权，契约生成链路也要重建——这些与"接入真实轨迹"没有依赖关系，混在一起会让 m2 变成巨型 milestone，验收说不清。
- **m3 只做"看得见的真实数据"**：来源同步 + 会话两页（列表/摘要）+ 家族树结构，问题卡先用空数组渲染（家族树没有红色卡片），保证这一阶段可独立演示；时间线页面已裁撤，不在任何 milestone 内。数据库以 MySQL 为主库、SQLite 仅测试，双库 CI 从 m3 第一天就跑。
- **m4/m5 只做打桩 UI**：把"UI 完成度"和"算法真实度"解耦；m4/m5 的验收是"与原型一致"，m6 才是"结论真实"。
- **m6 是占位实现的兑现**：只换执行器与聚类算法，不动前端、不动契约。

### 2.2 备选方案（更保守，5 个 milestone）

如果不想动现有编号：m2=平台骨架（含鉴权），m3=轨迹接入与归一化，m4=问题归因（外部只读），m5=自进化（占位执行）与接真合并（接真作为 m5 的后续批次）。代价：m5 同时承担"占位 UI 完整"与"换真实执行器"，验收标准会变成两页纸。**推荐 6 个**，但这是 roadmap 讨论的第一个问题（§5 Q1）。

## 3. Issue 草案

> 编号为草案序号（`m2-01` 形式），正式编号由 GitHub issue 分配。scope glob 为建议值，正式创建时按实际改动面收窄。

### 3.1 m2 平台骨架与契约（8 个）

| # | 标题 | 优先级 | scope | 依赖 | 验收 |
|---|---|---|---|---|---|
| m2-01 | 后端切换：新建 `apps/api`（FastAPI 骨架、配置、错误模型、health） | P0 | `apps/api/**`、`pnpm-workspace.yaml` | — | `/api/health` 返回 `phase=demo`；错误模型统一；`uv run pytest` 通过 |
| m2-02 | OpenAPI 契约生成链路与 CI 防漂移 | P0 | `packages/contracts/**`、`scripts/**` | m2-01 | `contract:generate` 产出类型；`contract:check` 在 CI 失败可复现 |
| m2-03 | 前端重建为 Vue 3（router/pinia/query/Element Plus/tokens/基元） | P0 | `apps/web/**` | m2-02 | 两大视图空壳可切换；设计令牌与原型一致 |
| m2-04 | PayloadSource 与 fixtures（`trajectory_payloads` 读取 + HttpApiSource 接口 + 演示种子数据） | P0 | `apps/api/app/service/acquisition/**`、`apps/api/app/third_party_api/**`、`fixtures/**` | m2-01 | payload 可读；fixtures seed 后 UI 可演示；无运行时桩分支 |
| m2-05 | SSE 事件总线与任务运行器骨架（job_runs + 串行 worker + 票据） | P1 | `apps/api/app/service/jobs.py`、`apps/api/app/service/events.py` | m2-01 | 订阅/发布/心跳/断线补发可用；job_runs 落状态；票据绑定 topics/cursor；重启可续 |
| m2-06 | 前端三态、全局错误处理、顶栏与演示数据角标 | P1 | `apps/web/src/**` | m2-03 | 空/加载/失败三态统一；`phase=demo` 显示角标 |
| m2-07 | 鉴权后端：users 表、登录/刷新/登出、JWT 中间件、初始管理员播种、SSE 票据 | P0 | `apps/api/app/modules/identity/**`、`apps/api/app/core/**` | m2-01 | 登录/刷新/登出链路通；错误密码 401；未登录访问业务 API 401；票据一次性 |
| m2-08 | 鉴权前端：登录页、auth store、http Bearer 注入与 401 刷新、路由守卫、顶栏用户区 | P0 | `apps/web/src/pages/login/**`、`apps/web/src/stores/**`、`apps/web/src/api/**` | m2-03、m2-07 | 未登录跳登录页；登录后回跳 redirect；access 过期自动 refresh；退出清态断 SSE |

### 3.2 m3 轨迹接入与归一化（9 个）

| # | 标题 | 优先级 | scope | 依赖 | 验收 |
|---|---|---|---|---|---|
| m3-01 | Database 接口 + SQLite / MySQL 两实现（连接、事务、health） | P0 | `apps/api/app/storage/**` | m2-01 | 默认 MySQL 可跑；SQLite 用于测试；`/api/health` 报告 dialect |
| m3-02 | Alembic 双方言迁移（真实表 + 预留表 + users/source_records/sync_*） | P0 | `apps/api/alembic/**` | m3-01 | 两种库空库 upgrade 建全表；重放脚本可跑 |
| m3-03 | 读 `trajectory_payloads` + 归一化幂等（hash/parser_version）与 fixtures 种子 | P0 | `apps/api/app/service/acquisition/**`、`fixtures/**` | m3-02 | 同一 payload 重复处理幂等；单条结构异常隔离；fixtures 可灌入真实表 |
| m3-04 | 归一化器（JSONL 行数组 → 轮次/步骤/块/token/元记录） | P0 | `apps/api/app/modules/acquisition/normalize.py` | m3-03 | 4 个会话的轮次/步骤/工具有数可对；坏行不毁整文件 |
| m3-05 | 家族组装（子转录、toolUseId、member_events 预计算） | P0 | `apps/api/app/modules/acquisition/family.py` | m3-04 | 子 agent 挂接位置正确；缺 toolUseId 有告警 |
| m3-06 | 会话 API（列表/摘要/家族树；统计读聚合列） | P0 | `apps/api/app/modules/sessions/**` | m3-05 | 4 种排序、密度口径符合 [05](05-api-design.md)；不提供时间线端点 |
| m3-07 | 前端 Session 列表 + 家族摘要 | P0 | `apps/web/src/pages/sessions/**` | m2-03、m3-06 | 与原型列表/摘要视觉一致；搜索/筛选/排序可用 |
| m3-08 | 后台定时调度与单飞锁（sync_lock）+ 顶栏状态 | P1 | `apps/api/app/service/acquisition/**`、`apps/api/app/service/jobs.py`、`apps/web/src/**` | m2-05、m3-03 | 定时处理 pending；手动幂等复用 jobId；无并发重复任务 |
| m3-09 | 上游轨迹查询契约定稿与 HttpApiSource | P1 | `apps/api/app/third_party_api/**`、`plans/**` | m3-03 | 契约（[05 §10](05-api-design.md)）评审通过；HttpApiSource 对 mock 上游联调通过（上游就绪前 payload 表先跑通） |

### 3.3 m4 问题与归因（打桩，6 个）

| # | 标题 | 优先级 | scope | 依赖 | 验收 |
|---|---|---|---|---|---|
| m4-01 | bad_case / probe 只读服务与 fixtures（外部表契约） | P0 | `apps/api/app/service/bad_cases/**`、`apps/api/app/service/probes/**`、`fixtures/**` | m2-04 | 列表/详情/状态合并正确；fixtures 覆盖 5 种展示状态 |
| m4-02 | bad_case / probe API（badCaseId 校验、probe 反查） | P0 | `apps/api/app/api/**`、`apps/api/app/service/**` | m4-01 | 深链字段齐全；跨会话 409；未分析占位 |
| m4-03 | 家族树布局移植与最小树验证 | P0 | `apps/web/src/components/family-tree/**` | m2-03 | `demo-nested` 四件事全对（归属/嵌套/折叠/连线不穿） |
| m4-04 | 家族树全量（节点链/问题卡锚定/折叠/fitView/定位） | P0 | 同上 | m4-03 | 4 个会话与原型一致；点击定位高亮 |
| m4-05 | 问题列表面板与定位联动 | P1 | `apps/web/src/components/bad-cases/**` | m4-02、m4-04 | 列表↔画布联动；badCaseId 新窗口打开 |
| m4-06 | 错误详情页（左栏/执行流过滤/双 Tab/深链恢复） | P0 | `apps/web/src/pages/errors/**` | m4-02、m4-04 | 六状态、全部错误恢复、tab 顺序、刷新恢复 |

### 3.4 m5 自进化闭环（9 个）

| # | 标题 | 优先级 | scope | 依赖 | 验收 |
|---|---|---|---|---|---|
| m5-01 | evolution 服务与状态机 + 占位聚类（按 attribute_type 分半） | P0 | `apps/api/app/service/evolution/**` | m2-04 | unit 推进边界正确；簇落库；同输入同输出 |
| m5-02 | 运行列表 API + 前端列表 | P0 | `apps/api/app/service/evolution/**`、`apps/web/src/pages/evolution/**` | m5-01 | running/history 分组；进度条与阶段文案后端给 |
| m5-03 | probe 查询 / 聚类预览 API + 启动向导 | P0 | 同上 | m5-01、m2-03 | 两步向导；命中统计；仅聚类出口（cluster_only run） |
| m5-04 | 运行详情六步 API（筛选/聚类/归因/排序/迭代/终评） | P0 | `apps/api/app/service/evolution/**` | m5-01 | 六步 payload 与 [05 §3.6](05-api-design.md) 一致 |
| m5-05 | 运行详情前端（stepper/各步内容/迭代卡/diff/eval/commit/分支信息） | P0 | `apps/web/src/pages/evolution/**` | m5-04 | 与原型详情一致；未到达不可点；展示分支/commit |
| m5-06 | 仅聚类页、模拟推进、运行中 SSE 进度联动 | P1 | 同上 + `apps/api/app/service/events.py` | m5-03、m5-05 | 仅 running 订阅；完成/离开即关闭；断线从 DB 回放进度不倒退 |
| m5-07 | 进化对象配置：CRUD API + 配置页 + 向导齿轮入口 | P0 | `apps/api/app/service/evolution/targets.py`、`apps/api/app/api/**`、`apps/web/src/pages/evolution/targets/**` | m5-01、m2-03 | 仅启用对象进向导；repo/ref 校验；删除被引用配置 409 |
| m5-08 | Workspace 与 git：clone tag、建 `evo/{YYYYMMDD}-{run_id}` 分支、candidate commit、amend/reset、完成后校验并 push | P0 | `apps/api/app/service/evolution/**`、`apps/api/app/service/jobs.py` | m5-01 | candidate 带追溯 commit；接纳 amend 追加评测；拒绝 reset；完成后 push 到远端 |
| m5-09 | 执行事件与异常：`evolution_run_events` 落库、events API、失败/中断/推送异常、前端日志面板 | P0 | `apps/api/app/service/evolution/events.py`、`apps/api/app/api/**`、`apps/web/src/pages/evolution/components/RunLogPanel.vue` | m5-01、m5-08 | 运行过程与异常刷新后可查；failed/interrupted 有摘要与脱敏详情 |

### 3.5 m6 接真实现（4 个，可拆到后续）

| # | 标题 | 优先级 | scope | 依赖 | 验收 |
|---|---|---|---|---|---|
| m6-01 | 真实轨迹接入生产化（`trajectory_payloads` + HttpApiSource 联调） | P1 | `apps/api/app/service/acquisition/**`、`apps/api/app/third_party_api/**` | m3-09 | payload 处理稳定；上游就绪后按需 pull；失败按条隔离 |
| m6-02 | 真实 patch 生成与评测执行器（替换占位值；本地或 CI） | P1 | `apps/api/app/service/evolution/**`、`apps/api/app/service/jobs.py` | m5-01 | 一条真实问题走完"patch → 评测 → 接纳/拒绝" |
| m6-03 | 聚类算法升级（替换占位分半算法） | P2 | `apps/api/app/service/evolution/**` | m5-01 | 新算法结果落 `probe_clusters`，表结构不变 |
| m6-04 | 外部问题/归因表契约联调与监控 | P1 | `apps/api/app/db/models/**`、`apps/api/app/service/bad_cases/**` | m4-01 | 上游表结构/状态变更可被发现（监控+告警），字段不一致有降级 |

## 4. 功能点覆盖检查

| 功能点 | m2 | m3 | m4 | m5 | m6 |
|---|---|---|---|---|---|
| F1 顶部导览 | ● | | | | |
| F2 ID 体系与深链 | · | | ● | | |
| F3 Session 列表 | | ● | | | |
| F4 家族摘要 | | ● | | | |
| F5 家族树 | | ●（结构） | ●（问题卡） | | |
| F6 会话内问题列表 | | | ● | | |
| F7 时间线（已裁撤） | — | — | — | — | — |
| F8 错误详情与归因 | | | ● | | ●（真实结论） |
| F9 轨迹接入与归一化 | | ● | | | ●（真实来源） |
| F10 运行列表 | | | | ● | |
| F11 启动向导 | | | | ● | |
| F12 仅聚类结果 | | | | ● | |
| F13 运行详情六步 | | | | ● | |
| F14 SSE 进度 | ●（机制） | | | ●（运行） | |
| F15 对象/模型清单 | ●（桩） | | | | ●（真实） |
| F16 模拟推进 | | | | ● | |
| F17 三态与错误处理 | ● | | | | |
| F18 登录与鉴权 | ● | | | | |
| F19 进化对象配置 | | | | ● | |
| F20 执行日志与异常 | | | | ● | |

## 5. 需要你拍板的路线图问题

1. **里程碑数量**：采用 §2 的 6 个（推荐，m2 单独做平台骨架），还是 §2.2 的 5 个（不动现有编号，骨架塞进 m2）？
2. **m6 是否现在纳入 roadmap**：纳入（推荐，明确打桩预留的兑现路径）还是等 m5 完成后再加？
3. **issue 粒度**：§3 的粒度（约 34 个）是否合适？还是要更细（如把"归一化"拆成轮次/块/token 三个）或更粗（按页面合并）？
4. **既有 m1 issue**：全部保持 `done` 不动，还是把"原型打磨"类 issue 关闭/归档？
5. **双语文件**：新增 milestone/issue 是否同步产出英文版（`flow:new-issue` 默认生成三件套）？还是允许先中文、后补英文（会触发 i18n 门禁）。

## 6. 确认后的执行步骤

```text
你确认设计 + 路线图问题
  ▼
更新 roadmap.md（m1..mN）
  ▼
重写/新建 milestones/*.md（三件套）
  ▼
pnpm flow:new-issue 生成 issue 三件套
  ▼
pnpm verify:flow 离线校验
  ▼
pnpm flow:sync 写 GitHub（需要时）
  ▼
按 m2 → m3 → … 顺序实现
```

- roadmap 与 milestone 的正文用"目标 / 范围 / 验收 / 非目标"四段式（与现有 m2 文件一致）。
- 每个 issue 的 scope 必须覆盖它真正会改的文件（含 `docs/`、`.agents/flow/` 自身），否则 `verify-flow --diff` 会拦。
- 文档确认后，我会把 01–09 的核心结论回写 `docs/architecture.md`（现状描述），决策理由进 `.agents/notes/`，保持仓库"一个事实一个 home"。
