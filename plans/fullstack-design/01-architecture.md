# 01 · 总体架构设计

> 本文回答：系统由哪几部分组成、数据怎么流动、外部数据怎么接入、部署形态是什么。
> 前置：[README · 文档地图与已确认决策](README.md)；下游：[02 功能点拆分](02-features.md)。
> 2026-10-22 重大修订：产品定位从"本地单机工具"改为 **SaaS 服务**，数据源从"本机文件扫描"改为"原始轨迹表 + 查询接口"。
> 2026-10-23 边界修订：第三方脚本只写原始 payload 表；本服务不负责采集/扫描源表，只做读取与归一化。

## 1. 系统边界

Harness Evolution 是一个 **SaaS 形态的组织内部服务**，不是装在本机上的工具：

- **输入**（两类轨迹来源，见 §4.1）：
  1. **原始轨迹表 `trajectory_payloads`**：第三方脚本把"有问题的 session 轨迹"（每 agent 一份 JSONL）写入 MySQL，本服务读取并归一化；采集不归本服务。
  2. **轨迹查询接口**：上游提供"Claude Code 轨迹 + 元数据"的查询 API（当前不存在，**契约由我们定义**，见 [05 §10](05-api-design.md)），按需 pull 后写入同一张 payload 表。
- **处理**：读取 payload → 归一化 → 存储（MySQL）→ 查询展示 → 问题与归因（外部只读）→ 自进化（**真实修改 skill/agent 文件并 commit 到 run 分支**）。
- **输出**：浏览器里的两大视图（Session 错误查看 / 自进化），以及推到远端的 **`evo/{YYYYMMDD}-{run_id}` 分支**；面向组织内全部登录用户，**单组织共享**。
- **不做什么**：**不采集/扫描外部源表**、**不在用户本机 `~/.claude` 目录直接改 skill**（只改配置的 skill 仓库副本）、不访问生产凭据、不做多租户、不做公网注册。

## 2. 组成与分层

```text
┌──────────────────────────────────────────────────────────────┐
│ 浏览器                                                       │
│   apps/web · Vue 3 SPA（登录态）                             │
└───────────────────────────┬──────────────────────────────────┘
                            │ REST（Bearer JWT）+ SSE（一次性票据）
┌───────────────────────────▼──────────────────────────────────┐
│ apps/api · FastAPI 模块化单体                                │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ HTTP 层：路由 · 鉴权 · 校验 · 错误模型 · SSE           │  │
│  └───────────────────────────┬────────────────────────────┘  │
│                              ▼                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 服务层：sessions / acquisition / bad_cases / probes    │  │
│  │         / evolution / identity                         │  │
│  └───────────────────────────┬────────────────────────────┘  │
│                              ▼                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 数据接入层：只读外部表 / 出站客户端 / fixtures         │  │
│  └───────────────────────────┬────────────────────────────┘  │
│                              ▼                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Repository：Database 接口 + SQLite / MySQL 适配        │  │
│  └───────────────────────────┬────────────────────────────┘  │
└──────────────────────────────┼───────────────────────────────┘
                               ▼
                 ┌──────────────────────────────┐
                 │ MySQL 8（主库）              │
                 │ 业务表 + payload 表 + users  │
                 └──────────────────────────────┘

轨迹输入：上游查询接口 / trajectory_payloads ──► 服务层（acquisition）
```

四层职责一句话各一句：

| 层 | 职责 | 不做什么 |
|---|---|---|
| HTTP 层 | 路由注册、鉴权中间件、请求/响应的 Pydantic 校验、统一错误模型、SSE 通道 | 不写业务判断 |
| 服务层 | 业务规则（筛选、排序、聚合、状态机推进、ID 生成、同步编排） | 不直接拼 SQL、不直接访问外部接口 |
| 数据接入 | 只读外部表（问题/归因）、出站客户端（上游轨迹）、fixtures（演示） | 不写外部表；不把演示数据混进运行时分支 |
| Repository 层 | 表的读写，只暴露领域对象 | 不含业务规则、不含方言字符串 |

依赖方向只允许向下：HTTP → 服务 → 数据接入/CRUD。

## 3. 模块划分（垂直切片）

```text
apps/api/app/
  main.py                 # 组装入口：建 app、挂中间件（含鉴权）、注册全部路由
  config.py               # pydantic-settings：DB、鉴权、来源、同步间隔（必要补充）
  api/                    # 各域 router（薄，只做参数校验与 DTO 映射）
  api_req/                # 请求 DTO（Pydantic）
  api_resp/               # 响应 DTO（OpenAPI 契约源头）
  constants/              # 枚举、错误码、issue/topic 常量
  db/
    session.py            # engine / session / 事务上下文
    models/               # SQLAlchemy 表模型（轨迹侧 + 问题侧只读表）
    crud/                 # BaseCrud + 各表 CRUD（方法接收 AsyncSession）
  middleware/             # request_id、JWT 鉴权（含路径规则）、CORS、登录限速
  service/
    identity/             # 登录、token、用户、SSE 票据
    sessions/             # 会话列表、会话概览、Agent 会话树
    acquisition/          # 轨迹来源、归一化、Agent 会话树组装、幂等写入
    bad_cases/            # 问题列表与详情（外部表只读）
    probes/               # 归因结论读取（外部表只读）
    evolution/            # run、占位聚类、六步产出、推进
    catalogs/             # 目标/模型清单（只读聚合）
    jobs.py               # 串行任务执行器（job_runs）
    events.py             # 进程内 SSE 事件总线
  schemas/                # service 层数据结构（跨层传递）
  third_party_api/        # 出站 HTTP 客户端（接口 + 实现成对）
    trajectory/           # 上游轨迹查询（上游待实现）
    llm/                  # 预留：LLM 调用（V1 不用）
  utils/                  # 纯工具（JSONL 行辅助、哈希、时间、JWT）
fixtures/                 # 演示种子数据 + app/cli.py seed
alembic/                  # 迁移（项目根）
```

> 与你给的结构相比只多了 `config.py`（配置必要）与项目根 `fixtures/`、`alembic/`；`providers/`、`jobs/` 不建：轨迹来源在 `service/acquisition` + `third_party_api`，任务执行在 `service/jobs.py`。

前端（详见 [03](03-frontend-architecture.md)）：

```text
apps/web/
  vitest.config.ts        # node / jsdom 两个测试 project
  src/
    api/                  # http/queryClient/queryKeys + 按域模块（auth/sessions/badCases/probes/evolution/acquisition/catalogs）
    composables/         # 每个域一个 useXxx + useAuth/useRunEvents/useTargets
    stores/              # Pinia：登录态（access token + 当前用户）、视图偏好；不存当前 session
    pages/
      login/             # 登录页
      sessions/          # Session 浏览器（列表 + 会话概览 + Agent 执行流图）
      errors/            # 错误详情与归因
      evolution/         # 运行列表 / 详情 / 仅聚类 / 对象配置
      evolution/components/  # Stepper/ClusterCard/DiffView/RunLogPanel/LaunchWizard 等页面专属件
    components/          # agent-tree / bad-cases / ui（含 IconRenderer）/ layout（跨页面共享）
    test/                # setup.ts + MSW server（测试用，不进 dev）
    router/              # 路由、深链、登录守卫
```

## 4. 数据流（四条主链路）

### 4.1 原始轨迹接入与归一化链路

```text
第三方脚本 ──写──► ┌───────────────────────┐
                   │ trajectory_payloads   │
上游接口 ──pull──► │ 每 agent 一行 JSONL   │
                   │ + hash + 行数         │
                   └───────────┬───────────┘
                               │ 读（按 root_session_id + agent_id）
                               ▼
                   ┌───────────────────────┐
                   │ source_records        │
                   │ 处理索引：root + agent│
                   │ processed_hash        │
                   │ parser_version        │
                   └───────────┬───────────┘
                               ▼
                   ┌──────────────────────────────┐
                   │ normalize                    │
                   │ JSONL -> 整树统计 / user_turns│
                   │ agent_events                 │
                   └──────────────┬───────────────┘
                               ▼
                   ┌─────────────────────────┐
                   │ tables                  │
                   │ session_families        │
                   │ agents                  │
                   │ user_turns              │
                   │ agent_events            │
                   └─────────────────────────┘
```

两类来源共用一个归一化管线：

| 来源 | 触发方式 | 读取内容 | 幂等键 |
|---|---|---|---|
| 第三方脚本写入的 `trajectory_payloads` | 后台定时（默认 60s）/ admin 手动 | 按 `(root_session_id, agent_id)` 取 JSONL 原文 | `(root_session_id, agent_id)` + `content_hash` + `parser_version` |
| 轨迹查询接口（上游待实现） | 用户手动 pull | 按 [05 §10](05-api-design.md) 契约返回的 payload | 同上 |

- **payload 只存一份**：`trajectory_payloads`；`source_records` 不存 payload，只存处理状态，需原文时按 `(root_session_id, agent_id)` 回查。
- 不再扫描 `he_src_*` 源表、不再维护水位线；待处理状态由 `source_records.processed_hash / parser_version` 表达。
- 归一化规则不变（[06 §7.1](06-database-design.md)）：用户轮次由"真实人类提问"派生、tool_result 回填、子转录按 `toolUseId` 挂接、Agent 会话树触发点预计算——**输入从 `Path` 变成 `list[str]`，解析器本身一行不改**。

### 4.2 查询链路（按模块拆分，页面并行加载）

页面不调用“一个整页接口”，而是按区块并行发起多个资源接口；每个接口只组装自己那块数据：

```text
浏览器 /sessions/:sid
   │
   ├──► GET /sessions/{sid} ──────────► sessions 服务 ──► session_families 表
   │                                      └──► summary 响应 ──┐
   │                                                          │
   ├──► GET /sessions/{sid}/tree ─────► sessions 服务 ──► agents / agent_events
   │                                      │                  + bad_cases
   │                                      └──► tree 响应 ─────┤
   │                                                          │
   └──► GET /sessions/{sid}/bad-cases ─► bad_cases 服务 ──► bad_cases / analysis / probe（只读）
                                          │                  + session_families（存在性校验）
                                          └──► bad-cases 响应 ┘
                                                               │
                                                               ▼
                                          前端按区块独立渲染（各自 skeleton，互不阻塞）
```

- **没有“整页单接口”**：三个请求由前端并行发出（vue-query 各自 queryKey），会话概览先到就先渲染，Agent 会话树/问题列表后到。
- 每个接口只做自己的服务组装：会话概览读 `session_families`；Agent 会话树读 `agents/agent_events` 并按 `bad_case_agent_id` 关联问题卡；问题列表读外部只读表并校验 `session` 存在。
- 问题详情页同理：先取 `/sessions/{sid}/bad-cases`，选中后再取 `/bad-cases/{id}`、`/analysis`、`/probes/{id}`（按需串行，不是整页一次拉完）。
- 页面级聚合仅用于**列表页**（`GET /sessions`、`GET /evolution/runs`）和**静态元数据**（`/catalogs`、向导的 targets meta），不用于详情页的“大杂烩”响应。

前端拿到的每个响应只覆盖一个模块；问题侧数据由外部系统写入，本服务只读。单组织共享下无行级过滤，`principal` 只记录进审计字段（`created_by`）。

### 4.3 任务、自进化与 SSE 链路

原则：**REST 负责首屏与事实，SSE 只在“正在执行”时做增量通知；已完成任务不建 SSE。**

#### 4.3.1 自进化页面：打开列表、启动、查看历史

```text
打开 /evolution
  → GET /evolution/runs
  → 渲染「正在执行」「历史记录」
     ├─ 点击「启动自进化」
     │    → 向导 /probes/query → 命中确认
     │    → POST /evolution/runs → 202 {runId, status:"preparing"}
     │    → 路由 /evolution/runs/:rid
     └─ 点击历史 run
          → 路由 /evolution/runs/:rid
```

#### 4.3.2 运行详情：先 REST 初版，再按状态决定是否 SSE

```text
打开 /evolution/runs/:rid
  → 并行 REST：
       GET /runs/:rid
       GET /runs/:rid/steps/{currentKey}
       GET /runs/:rid/events?afterSeq=0（分页拉完，记录最后 seq）
  → 渲染初版
  → status in {preparing, running} ?
       ├─ 是：
       │    POST /events/ticket {topics:["run:{rid}"], lastEventId: 已加载最后 seq}
       │    → GET /events?ticket=…
       │    → run.event / run.progress → append + 失效 queryKey
       │    → run.blocked → 显示重试；run.completed/failed/interrupted → close + 最后 REST 刷新
       └─ 否：
            不取 ticket、不建 SSE；blocked 走轮询/重试，终态翻 step / 日志走 REST
```

> `lastEventId` 必须用**已加载的最后一条事件 seq**，不能用 `run.lastEventSeq` 的最大值；否则 events 分页未拉完时会丢中间事件。

#### 4.3.3 自进化执行链：prepare → advance → eval → apply

```text
POST /runs（同步校验 target/probe）
  → run(preparing)
  → evolution_prepare job
       → 查 probe → simple_cluster
       → workspace clone / 建 run 分支
       → clusters / evolution_rounds
       → run(running)
  → evolution_advance job（每轮）
       → patch → candidate commit
       → push candidate ref（3 次立即 / 5s）
       → submit eval → evalId
       → round(evaluating)
  → eval_poller（每 5 分钟）
       → completed → evolution_apply job
       → failed/timeout → run(blocked, stage=eval)
  → evolution_apply job
       → 接纳：amend → push candidate → ff run 分支 → push run 分支 → 删 candidate
       → 拒绝：删 candidate → 切回 run 分支
       → 下一轮 / finalize
```

- push 是评测前置条件：candidate 先推临时 ref，再提交评测；push 3 次失败后 run `blocked`，不进入评测。
- 自动退避：1min / 5min / 15min 各 1 次 push；仍失败保持 `blocked`，等 `/retry`。
- 生产 UI 没有“推进一轮”；自动逐轮执行，SSE 只展示过程。
- `POST /runs/{rid}/retry` 是 blocked 后的人工恢复入口（所有登录用户，202 jobId）。

#### 4.3.4 轨迹归一化：后台定时处理 + 单飞锁

这里的「同步」**不是采集，也不是自进化**：它处理第三方脚本已经写入 `trajectory_payloads` 的原始 JSONL，归一化写入 `session_families / agents / user_turns / agent_events`。消息与内容块只在解析期用于统计和状态判定，不落库；需要原文时从 payload 回读。

```text
lifespan 启动 scheduler（默认每 60s）
  → 有 pending payload？
       ├─ 否：跳过
       └─ 是：抢 sync_lock
             ├─ 失败：已有同步任务，跳过
             └─ 成功：job_runs 入队 → 串行 worker 处理 → 释放锁

admin / 运维手动触发：
POST /acquisition/sync
  → 抢 sync_lock
       ├─ 失败：202 { jobId: 正在执行的任务, reused: true }
       └─ 成功：202 { jobId: 新任务, reused: false }
```

- **读路径不触发同步**：Session 页、自进化查询都只读，不做“发现没处理就顺手同步”。没处理的 session 在 `session_families` 里不存在，自然查不到。
- **自进化查询仍是 `probe_reports INNER JOIN session_families`**：session 未归一化 → probe 不可见；不做 preflight，也不返回 `DATA_NOT_READY`。
- **单飞锁**：`sync_lock` 单行表（`name='sync'`）+ `job_id/acquired_at/expires_at`；`INSERT` 主键冲突即已有任务。
- V1 单实例再加进程内 `asyncio.Lock` 兜底；多实例用 DB 行锁 / MySQL `GET_LOCK`。
- `job_runs` 同 `kind=sync` 只允许一个 `queued/running`，作为第二道保险。
- 锁 TTL 30 分钟；进程崩溃后下一次 tick 可回收。
- 手动触发只作为 admin/运维的“立即处理”，普通用户在顶栏只看到 pending 状态，不提供按钮。
- **同步没有 SSE topic**：进度通过 `GET /acquisition/status` / `GET /jobs/{jobId}` 查询，前端定时轮询即可；不占 SSE 连接。
- **没有全局 SSE**：App.vue 不建立常驻连接；只有 `preparing/running` 的 run 页面才订阅 `run:{rid}`。

### 4.4 鉴权链路

```text
┌─────────┐      ┌─────────┐      ┌──────────┐
│ Vue SPA │      │ FastAPI │      │ users 表 │
└───┬─────┘      └────┬────┘      └────┬─────┘
    │ POST /api/auth/login {username, password}
    ├──────────────────►│
    │                   │ 校验密码哈希（argon2）
    │                   ├────────────────►│
    │                   │◄────────────────┤
    │◄── accessToken(30min) + user ───────┤
    │    refreshToken（httpOnly cookie, 14d）
    │ GET /api/…（Authorization: Bearer）
    ├──────────────────►│
    │                   │ JWT 中间件 → RequestContext.principal
    │                   │
    │ [accessToken 过期] → POST /api/auth/refresh（cookie）
    ├──────────────────►│
    │◄──────────── 新 accessToken ────────┤
    │ POST /api/events/ticket（Bearer）
    │   { topics:["run:{rid}"], lastEventId } → {ticket, 60s}
    ├──────────────────►│
    │ GET /api/events?ticket=…（SSE）
    ├──────────────────►│
```

- EventSource 不能自定义请求头，SSE 用**一次性短票据**（查询参数），不用长期 token。
- refresh token 用 httpOnly + SameSite=Strict cookie，SPA 不接触；access token 只存内存（Pinia），刷新页面时先走 refresh。

## 5. 数据来源、外部表与演示数据

### 5.1 三类数据，三种处理方式

```text
┌─ 轨迹（本服务写业务表） ──────────────────────────────────────────┐
│ trajectory_payloads / 上游 API ──► acquisition ──► session_families/agents/… │
└───────────────────────────────────────────────────────────────────┘

┌─ 问题与归因（外部写，本服务只读） ────────────────────────────────┐
│ 外部上报/归因系统 ──► bad_cases / analysis / probe ──► bad_cases/probes 服务 │
└───────────────────────────────────────────────┬───────────────────┘
                                                │ 只读
                                                ▼
┌─ 自进化（本服务写） ──────────────────────────────────────────────┐
│ evolution ──► evolution_runs / probe_clusters / evolution_rounds        │
└───────────────────────────────────────────────────────────────────┘

fixtures/ + seed（仅开发） ┄┄► 业务表 / 问题表
```

| 数据 | 写入方 | 本服务 | 接入方式 |
|---|---|---|---|
| 原始轨迹（每 agent JSONL） | 第三方脚本；pull 时本服务写入 | **只读**（pull 除外） | `trajectory_payloads` |
| 轨迹业务表（session_families/agents/...） | 本服务归一化 | 读写 | `service/acquisition` + `source_records` |
| 问题与归因（bad_cases / analysis / probe） | 外部系统 | **只读** | `db/models` 只读表 + `db/crud` |
| 自进化（runs / clusters / evolution_rounds / finals） | 本服务 | 读写 | `service/evolution` |
| 用户、任务审计 | 本服务 | 读写 | `service/identity`、`service/jobs.py` |

### 5.2 没有统一 Provider 层（2026-10-22 修订）

早期设计的"六类 Provider + 全量桩实现"已取消，原因：问题/归因数据由外部系统写入表，真实实现读表即可；强行加一层 Provider 只会把"读表"包成假接口。现在只有三种接缝：

1. **出站调用** → `third_party_api/`（轨迹查询接口，未来 LLM/CI），接口 + 实现成对；
2. **外部表** → `db/models` 只读映射 + `db/crud`，表契约即接口；
3. **演示数据** → `fixtures/` + `app/cli.py seed`，仅开发/演示时灌入真实表，**运行时没有 stub 分支**。

### 5.3 演示数据（fixtures）的边界

- `fixtures/` 内含原型 4 个会话、若干 bad_case / probe，以及可选的 `evolution_targets` 配置；`python -m app.cli seed` 写入真实表；
- `probe_clusters` / `probe_cluster_probes` 是派生数据，不由 seed 写入；seed 后从向导启动，聚类由 `simple_cluster` 生成；
- 生产环境不执行 seed；UI 读到的永远是真实表；
- 与早期 D4 的差别：**不再有"Stub Provider 返回不入库数据"的运行时分支**，桩数据也从正式表结构走，避免字段对不上。

### 5.4 V1 的占位实现（不是 Provider）

| 占位点 | 位置 | 后续替换 |
|---|---|---|
| 聚类算法 | `service/evolution/simple_cluster`（按 attribute_type 分半） | 换真正的聚类实现，表不变 |
| patch 内容 | `service/evolution/patch.py` | 内容占位，但**真实写文件、真实 commit**；后续换 LLM/规则生成 |
| eval / 终评 | `service/evolution/eval.py` | 分数占位；后续换真实评测 |
| 上游轨迹接口 | 未配置时 `HttpApiSource` 不可用 | 上游就绪后启用 |
| git 推送 | `HE_GIT_PUSH=true`（每轮 candidate 评测前 push） | candidate ref 先推、评测后再 fast-forward run 分支；失败进入 blocked，3 次立即 + 1/5/15min 退避；后续开 PR |

## 6. 部署形态与扩展路径

**当前形态：单实例 SaaS**（一个 FastAPI 进程 + 一个 MySQL + 静态前端）：

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8787   # 生产主库 MySQL
pnpm --filter web build                            # 前端构建产物由 FastAPI StaticFiles 或 nginx 托管
```

| 维度 | 现在 | 扩展路径 |
|---|---|---|
| 用户 | 自建账号 + JWT，单组织共享 | 需要 SSO 时加 OIDC Provider（鉴权是独立接缝） |
| 数据库 | MySQL 8 主库；SQLite 仅测试/本地开发 | 读写分离/分库暂无需求 |
| 任务 | `job_runs` 表 + 进程内串行 worker | 多实例时 worker 独立部署（同一 `job_runs` 表，`SELECT … FOR UPDATE SKIP LOCKED` 抢占） |
| SSE | 内存事件总线（单实例） | 多实例时换 Redis pub/sub（EventBus 已是接口） |
| 进化产物 | 远端 `evo/{YYYYMMDD}-{run_id}` 分支 + 每轮临时 `.../candidate/r{n}` ref | 接纳后 fast-forward run 分支；拒绝删除 candidate；后续开 PR / 打 tag |
| 静态资源 | FastAPI `StaticFiles` | 换 nginx / CDN 无需改前端 |
| CORS | 配置的正式域名 | 同源托管后可关闭 |

## 7. 非功能设计要点

| 主题 | 决策 | 理由 |
|---|---|---|
| 鉴权 | 自建账号 + JWT；access 30min（内存）+ refresh 14d（httpOnly cookie）；SSE 一次性票据 | 不依赖外部 SSO；EventSource 不能带头的限制用票据绕开 |
| 首次启动 | users 表为空时用 `HE_ADMIN_USERNAME`/`HE_ADMIN_PASSWORD` 播种初始管理员 | 不自注册；后续用户由管理员创建 |
| 同步幂等 | `(root_session_id, agent_id)` + content hash + parser_version，重复处理零副作用 | 上游重推/重拉不得产生重复数据 |
| 大轨迹 | Agent 会话树触发点处理时预计算；轨迹聚合统计入库时冗余（跨写入方的派生值如问题数除外，查询时聚合）；payload 原文单独表（外部写） | 375 条消息 / 57 个子 agent 的会话存在，不能查询时重算 |
| 契约防漂移 | OpenAPI 生成物进 `packages/contracts`，CI 校验"重新生成 = 无 diff" | D3 决策的执行保障 |
| 错误模型 | 全 API 统一 `{error:{code,message,details}}`；401/403 有独立 code | 前端一个拦截器处理所有失败态 |
| 深链可恢复 | 选中 session / bad_case / tab / step 全在 URL（真实 ID） | badCaseId / probeId 跨页溯源的载体 |
| 可观测 | 结构化日志 + sync_runs / job_runs / evolution_run_events 留痕；不打印轨迹原文 | 轨迹可能含敏感内容；异常需在 UI 可查 |
| 数据库可替换 | `Database` 接口 + SQLite/MySQL 适配器 | 测试用 SQLite 快跑；生产 MySQL |
| 自进化隔离 | 每次 run 独立 workspace + 新分支；只改配置仓库副本，绝不写用户 `~/.claude` | 不污染用户环境、可回滚、可复现；candidate commit 在评测后 amend 或 reset |

## 8. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 上游查询接口迟迟不实现 | pull 来源一直空着 | 契约先行 + 脚本 payload 先跑通；上游就绪只换适配器（[05 §10](05-api-design.md)） |
| payload 表结构与预期不一致 | 归一化失败 | payload 契约写入文档并约版本号；解析失败隔离到单条记录（不毁整批），错误进 `sync_runs.errors` |
| Vue Flow 与 React Flow 的 API 差异 | Agent 执行流图移植返工 | 布局几何纯 TS 迁移，先做 `demo-nested` 最小树验证；`×N` 改为 message 口径（[08 §3](08-frontend-implementation.md)） |
| 外部表契约 | 外部表结构/字段与文档漂移 | 表契约评审 + 查询层防御（字段缺失降级、日志告警）；fixtures 与真实表同构 |
| git 操作失败 | 分支/commit 失败导致 run 卡住 | 每步幂等 + 失败标 `failed` 并保留工作区；错误含 stderr 摘要；串行执行避免并发写仓库 |
| 仓库配置错误 | clone/tag 不存在 | 保存配置时校验 `repo_url`/`ref`/`sub_dir`；启动 run 前再校验一次，失败 `422 REPO_INVALID` |
| 工作区残留 | 磁盘增长 | 默认保留最近 20 个 run，`clean-workspaces` 命令清理；不自动删进行中的 run |
| push 失败 | 评测无法开始，流程阻塞 | run 标 `blocked` + `blocked_stage=push`；保留 candidate ref；3 次立即 + 1/5/15min 退避；仍失败等 `/retry`；run 分支不被回滚 |
| 执行异常未留痕 | 无法定位/复盘 | 阶段/候选/评测/推送/异常统一写 `evolution_run_events`；job 边界捕获；启动扫描残留任务记 `interrupted` |
| JWT 泄漏 | 组织数据暴露 | access token 短命 + 只在内存；refresh httpOnly + SameSite=Strict；所有流量走 HTTPS |
| SSE 长连接在代理下断流 | 进度不更新 | 事件带 seq + Last-Event-ID；run 事件从 DB 回放，sync 用 job_runs + REST 兜底 |
| 单实例宕机 | 全员不可用 | 单组织内部工具可接受；`job_runs` 持久化保证重启续跑，横向扩展路径见 §6 |
