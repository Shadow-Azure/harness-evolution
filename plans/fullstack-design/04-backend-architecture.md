# 04 · 后端架构与组件选型

> 本文回答：后端用什么技术搭、怎么分层、外部数据怎么接、任务与 SSE 怎么工作、如何扩展。
> 前置：[01 总体架构](01-architecture.md)；下游：[06 数据库设计](06-database-design.md) · [07 后端实现设计](07-backend-implementation.md)。

## 1. 一句话架构

**Python 3.12 + FastAPI 模块化单体（SaaS 服务）**：HTTP 层只做校验、鉴权与路由，service 层承载业务规则，DB 层通过 `Database` 接口 + crud 访问 MySQL（SQLite 仅测试）；外部数据（问题/归因）以只读表接入，出站调用封装在 `third_party_api`；任务由 `service/jobs.py` 串行执行，进度走 `service/events.py` 的 SSE 总线。

## 2. 技术选型总表

| 类别 | 选型 | 角色 | 说明 / 备选 |
|---|---|---|---|
| 语言/运行时 | Python 3.12 | 后端全部 | 3.11+ 即可；`asyncio.TaskGroup` 可用 |
| Web 框架 | FastAPI | HTTP + 自动 OpenAPI | Pydantic v2 校验、依赖注入、SSE 友好 |
| ASGI 服务器 | uvicorn（dev `--reload`） | 运行 | 单实例起步；多实例时 worker 与 SSE 单独扩展（§8） |
| 数据校验/序列化 | Pydantic v2 | 领域模型 = 契约源头 | `model_config = ConfigDict(extra="forbid")` 防止契约偷偷膨胀 |
| 配置 | pydantic-settings | env → 配置对象 | `.env` 本地、不提交；密钥不进仓库 |
| 鉴权 | **PyJWT + argon2-cffi** | 自建账号登录 | access JWT（30min）+ refresh（httpOnly cookie，14d）；密码哈希 argon2 |
| ORM | **SQLAlchemy 2.0（async）** | 真实数据存储 | 表达式层跨方言；见 §2.1 与 §4 |
| 数据库驱动 | `asyncmy`（MySQL，主库）/ `aiosqlite`（测试） | 连接驱动 | 驱动差异被 `Database` 适配器吸收；备选 `aiomysql`（生态更老但稳） |
| 迁移 | Alembic（单版本树，双方言） | 版本化建表/改表 | SQLite 用 batch 模式；`alembic upgrade head` 由启动脚本执行 |
| 包管理 | **venv + pip** | 依赖与虚拟环境 | `python -m venv .venv` + `pip install -e ".[dev]"`；依赖声明在 `pyproject.toml`，虚拟环境不入库 |
| SSE | sse-starlette | 事件流 | 小型成熟库，自带心跳与断线处理；也可手写 `StreamingResponse` |
| HTTP 客户端（测试/未来 LLM） | httpx | API 测试 | `AsyncClient` + `ASGITransport` |
| 测试 | pytest + pytest-asyncio | 单测/接口测试 | 覆盖同步幂等、状态机、只读查询；MySQL 用可选 integration 标记 |
| 代码质量 | ruff（lint+format）、mypy（strict 模式渐进） | 门禁 | 与前端 lint/typecheck 对齐 |
| 任务队列（未来） | arq / CI 平台 | 替换串行执行器 | V1 不需要；接口先行（§7.3） |
| 契约生成（前端侧） | openapi-typescript | `apps/api` OpenAPI → TS | 见 [03 §10](03-frontend-architecture.md) |

> **驱动 vs ORM**：`asyncmy` / `aiosqlite` 是数据库驱动（DBAPI 层，只负责连接数据库、发送 SQL、返回结果）；SQLAlchemy 是 ORM/SQL 工具层，通过 dialect 调用驱动。`mysql+asyncmy://` 中 `mysql` 是方言，`asyncmy` 是驱动；`sqlite+aiosqlite://` 同理。两者不是同一层，也不是二选一。
>
> **venv + pip**：用标准库 `venv` 创建 `.venv`，激活后 `pip install -e ".[dev]"` 安装项目与开发依赖；`pyproject.toml` 只做依赖与构建元数据。项目不引入额外包管理器或锁文件；CI 使用同一套 `python -m venv` + `pip install` 命令。

### 2.1 为什么是 SQLAlchemy 2.0 而不是 SQLModel

| 维度 | SQLAlchemy 2.0 + Alembic + 独立 Pydantic 模型 | SQLModel（FastAPI 作者出品） |
|---|---|---|
| 表达力 | 完整（复合索引、JSON、CHECK、原生 SQL 逃生口） | 受限于"一个类既是表又是 API 模型"的折中 |
| 迁移 | Alembic 生态成熟，autogenerate 稳定 | 底层仍是 SQLAlchemy + Alembic，但双身份类让 autogenerate 偶有歧义 |
| 分层清晰度 | 表模型（db）与 API 模型（api_req/api_resp）分离，正好匹配本方案的 CRUD/只读外部表分层 | 容易把"表字段"直接暴露成 API 字段，契约被存储细节绑架 |
| 团队认知 | Python 生态默认选择 | 小众但简洁 |
| 结论 | ✅ 采用 | 不采用 |

代价是每个实体要写两套模型（`db/models/` 的表模型 + `api_req/api_resp` 的 DTO），换来的边界清晰是只读外部表与契约稳定所需要的——**API DTO 与表结构解耦，外部表字段变化不会直接漏进契约**。

## 3. 分层与目录

```text
┌─ HTTP 层（api/*.py） ─────────────────────────────────────────┐
│ 参数校验 · 响应模型 · 状态码                                  │
│ SSE 端点（events）                                            │
└───────────────────────────┬───────────────────────────────────┘
                            ▼
┌─ 服务层（service/*） ─────────────────────────────────────────┐
│ 业务规则 · 聚合 · 状态机 · ID 生成                            │
└───────────────┬───────────────────────────────┬───────────────┘
                ▼                               ▼
┌─ 外部数据接入 ──────────────────┐  ┌─ 存储层（db/） ─────────────┐
│ bad_cases/analysis/probe 只读   │  │ Database 接口 + SQLite/MySQL│
│ 上游轨迹 API（third_party_api） │  │ CRUD（方言无关）            │
└───────────────┬─────────────────┘  │ Alembic 迁移（双方言）      │
                └───────────────────►└─────────────────────────────┘

┌─ 基础设施（middleware/ service/jobs · events） ───────────────┐
│ 错误模型 · 请求上下文 · 日志                                  │
│ 任务运行器 · SSE 事件总线                                     │
└───────────────────────────────────────────────────────────────┘
```

```text
apps/api/
  pyproject.toml
  app/
    main.py                  # create_app()：中间件（含 JWT 鉴权）、异常处理、路由注册（唯一注册点）
    config.py                # Settings：DB、鉴权、来源、同步间隔
    api/                     # 各域 router（薄层）
      auth.py  sessions.py  acquisition.py  bad_cases.py  probes.py  evolution.py  catalogs.py  events.py
    api_req/                 # 请求 DTO（Pydantic）
    api_resp/                # 响应 DTO（OpenAPI 契约源头）
    constants/               # 枚举、错误码、issue/topic 常量
    db/
      session.py             # engine / session / transaction / health
      sqlite.py              # SqliteDatabase：aiosqlite + WAL/PRAGMA
      mysql.py               # MySqlDatabase：asyncmy + 连接池/utf8mb4
      factory.py             # create_database(settings)：按 HE_DB_DIALECT 装配
      models/                # SQLAlchemy 表模型（轨迹侧 + 问题侧只读）
      crud/                  # BaseCrud + 各表 CRUD（接收 AsyncSession）
    middleware/
      request_id.py  auth.py  cors.py  rate_limit.py
    service/
      identity/              # 登录、token、用户、SSE 票据
      sessions/              # 列表/会话概览/Agent 会话树
      acquisition/           # 读 payload、归一化、Agent 会话树组装、定时调度（scheduler.py）
      bad_cases/             # 问题列表/详情（只读）
      probes/                # 归因结论（只读）
      evolution/             # run、聚类、candidate push、eval gateway/poller、apply、blocked retry、事件
      catalogs/              # 目标/模型清单
      jobs.py                # 串行任务执行器（job_runs）
      events.py              # 进程内 SSE 事件总线
    schemas/                 # service 数据结构
    third_party_api/
      trajectory/            # 上游轨迹查询：client.py + http_client.py
      llm/                   # 预留：client.py + openai_client.py
    utils/                   # 纯工具（JSONL 行辅助、哈希、时间、JWT）
  tests/
    conftest.py              # 参数化 DB fixture：默认 SQLite，-m mysql 时用 MySQL
    test_acquisition.py  test_sessions.py  test_bad_cases.py
    test_evolution.py  test_jobs.py  test_events.py  test_openapi.py
fixtures/                    # 演示种子数据（app/cli.py seed）
alembic/                     # 迁移（项目根，与 app 平级）
```

**路由只在 `main.py` 注册**（沿用仓库现有约定），各域提供 `router = APIRouter(prefix=...)`。

## 4. 数据库设计：MySQL 主库 / SQLite 测试

### 4.1 目标与边界

- **MySQL 8 是生产主库**；SQLite 只用于测试与本地开发（快跑、免装库）。
- 切换时**只改配置**：业务代码、CRUD、API 契约、前端、迁移版本都不变。
- 抽象只做两层：`Database`（连接、方言、事务、健康检查）与 `CRUD`（查询）。**不**为 SQLite/MySQL 各写一套 CRUD——那会把同一份业务逻辑复制两遍，必然漂移。

```text
HE_DB_DIALECT=sqlite|mysql
           │
           ▼
     db/factory.py
       ├──► SqliteDatabase（aiosqlite + WAL） ──┐
       └──► MySqlDatabase（asyncmy + 连接池） ──┤
                                                ▼
                                     Database Protocol
                                                ▲
                      db/crud/*（同一套实现） ───┤
                      service/* ──► crud ───────┘
```

### 4.2 `Database` 接口

`storage/database.py` 用 `Protocol` 定义连接生命周期；业务与 Repository 只依赖它：

```python
class Database(Protocol):
    dialect: str                      # "sqlite" | "mysql"
    async def start(self) -> None: ...            # 建 engine，跑连通性检查
    async def dispose(self) -> None: ...
    def session(self) -> AsyncSession: ...        # 只读查询用
    def transaction(self) -> AsyncContextManager[AsyncSession]: ...  # 写操作用
    async def health(self) -> DBHealth: ...       # (ok, dialect, latency_ms)
```

纪律：

- Repository 内只用 SQLAlchemy 表达式（`select/insert/update/delete`），**不出现方言字符串**。
- 需要方言差异时（如 upsert），走 SQLAlchemy 的 dialect 分支或"先查后写"的通用实现，不把 SQL 字符串散落到业务层。
- FastAPI 用 `Depends(get_database)` 注入；测试用 `app.dependency_overrides` 换成临时库（SQLite 文件或 MySQL 测试库），业务代码不感知。
- `Database.health()` 供 `/api/health` 使用：DB 不可达时 `ok=false`、`db.ok=false`，API 进程仍可启动并给出明确错误。

### 4.3 两个实现

| 实现 | 连接串 | 关键配置 |
|---|---|---|
| `SqliteDatabase` | `sqlite+aiosqlite:///{HE_DATA_DIR}/harness.db` | 连接时 `PRAGMA journal_mode=WAL`、`foreign_keys=ON`、`busy_timeout=5000`、`synchronous=NORMAL`；适合单进程调试 |
| `MySqlDatabase` | `mysql+asyncmy://{user}:{pass}@{host}:{port}/{db}?charset=utf8mb4` | `pool_size` / `max_overflow` / `pool_recycle=1800` / `pool_pre_ping=True`；连接初始化 `time_zone='+08:00'`；库与表统一 `utf8mb4_0900_ai_ci` |

`storage/factory.py` 是唯一选择点：

```python
def create_database(settings: Settings) -> Database:
    if settings.db_dialect == "sqlite":
        return SqliteDatabase(settings)
    if settings.db_dialect == "mysql":
        return MySqlDatabase(settings)
    raise ConfigError(f"unknown HE_DB_DIALECT: {settings.db_dialect}")  # fail fast
```

### 4.4 切换步骤（调试 → 上线）

```text
本地 SQLite（测试）──► MySQL 8（生产主库）──► HE_DB_DIALECT=mysql + URL
        ──► 启动 alembic upgrade head
        ──► POST /api/acquisition/sync 重跑归一化（payload 表仍是真相）
        ──► pytest -m mysql 跑同一套 CRUD 测试
        ──► 回退同样只改配置
```

- **不需要写数据迁移脚本**：换库后重跑归一化即可（`trajectory_payloads` 仍是事实源）；问题侧数据由外部系统重新灌入；演示数据用 `fixtures` seed 重建。
- **切换是启动期配置**（改 env 后重启生效），不做运行时热切换——避免同一进程同时连两个库造成数据分裂。
- Alembic 用**一棵版本树、双方言渲染**；SQLite 的 `ALTER TABLE` 限制用 `render_as_batch=True` 处理。
- CI 两条：默认 SQLite 快跑；MySQL 任务（service container）跑 `-m mysql` 标记的集成测试，防止"只在小库上绿"。

### 4.5 跨库 SQL 纪律（写代码时的硬约束）

| 约束 | 原因 | 做法 |
|---|---|---|
| 不用 `INSERT OR REPLACE` / `ON DUPLICATE KEY` 裸写 | 两种方言语法不同 | 跨库默认"先查后写"包在事务里；确需 upsert 时用 SQLAlchemy 方言构造（SQLite `on_conflict_do_update` / MySQL `on_duplicate_key_update`）封装在 Repository 内 |
| 索引列不用 `TEXT` | MySQL 索引键长上限（3072 字节） | 索引/唯一键列用 `VARCHAR(n)`（n ≤ 255）；正文用 `MEDIUMTEXT` 且不建索引 |
| 不依赖 `LIKE` 的大小写行为 | SQLite ASCII 不敏感、MySQL 取决于 collation | 写入时维护 `search_text`（lower），查询统一 `LIKE` 该列 |
| JSON 不在 SQL 里查 | SQLite JSON1 与 MySQL JSON 函数不同 | JSON 列只做整存整取（`sa.JSON`），过滤在 Python 侧做（数据量小） |
| 时间统一 Asia/Shanghai | 两种库时区语义不同 | `DateTime(timezone=True)` + 应用层写 `Asia/Shanghai`；API 输出 `+08:00`；禁止 `NOW()` 默认值 |
| 自增主键 | SQLite `INTEGER PRIMARY KEY` vs MySQL `BIGINT AUTO_INCREMENT` | SQLAlchemy `Integer primary_key=True autoincrement=True`，迁移里由方言渲染 |
| 事务边界 | SQLite 整库写锁，MySQL 行锁 | 写操作统一走 `Database.transaction()`；不依赖"自动提交" |

## 5. 数据接入：只读外部表 + 出站调用 + fixtures

### 5.1 三类接缝（不再有统一 Provider 层）

| 接缝 | 位置 | 说明 |
|---|---|---|
| 原始轨迹 | `service/acquisition/payloads.py` + `third_party_api/trajectory/` | 读 `trajectory_payloads`（外部脚本写）；pull 时写入同一张表 |
| 问题/归因 | `db/models/` 只读映射 + `db/crud/` | `bad_cases` / `bad_case_analysis` / `probe_reports` 由外部系统写入，本服务只读 |
| 演示数据 | `fixtures/` + `app/cli.py seed` | 仅开发/演示时灌入真实表，运行时无 stub 分支 |

早期"六类 Provider + stub 实现"的设计已取消：问题/归因数据本来就在外部表里，真实实现是"读表"，不需要再包一层可替换接口；强行抽象只会增加映射代码和漂移风险。

### 5.2 原始 payload 与归一化

```python
class PayloadSource(Protocol):
    async def list_pending(self, parser_version: int) -> list[PendingPayload]: ...
    async def get(self, root_session_id: str, agent_id: str) -> TrajectoryPayload: ...   # root/agent/kind/JSONL
    async def upsert_many(self, payloads: list[TrajectoryPayload]) -> None: ...  # 仅 pull 使用
```

| 实现 | 读取/写入 | 启用条件 |
|---|---|---|
| `MySqlPayloadSource` | 读 `trajectory_payloads`（`root_session_id`、`agent_id`、`payload`、`agent_meta`、`content_hash`、`line_count`） | V1 默认；**不扫描 `he_src_*`** |
| `HttpApiSource` | 调上游接口，把返回 payload upsert 到 `trajectory_payloads` | 上游就绪后配置启用；`third_party_api/trajectory/http_client.py` |

- **payload 只存一份**：`trajectory_payloads`；`source_records` 只是处理索引，不存 payload。
- 待处理判定：`source_records` 无记录，或 `processed_hash != payload.content_hash`，或 `parser_version < 当前版本`。
- 没有水位线；`source_records.processed_*` 就是游标。

### 5.3 fixtures：演示数据的唯一形态

- `fixtures/` 放原型 4 个会话的轨迹、bad_cases、probes，以及可选的 `evolution_targets` 配置；
- `probe_clusters` / `probe_cluster_probes` 是**派生数据，不写入 fixtures**；seed 后在向导启动 `POST /evolution/cluster-previews` 或 `POST /evolution/runs`，由 `simple_cluster` 生成；
- `python -m app.cli seed` 幂等写入真实表（按主键 upsert 语义），仅开发/演示环境执行；
- 生产不执行 seed；UI 永远读真实表；
- 与"运行时 Stub Provider"的区别：没有 `phase=demo` 之外的运行时分支逻辑，问题侧字段与真实表完全一致（`demo` 只表示数据来自 seed）。

### 5.4 V1 占位实现（在 service 内，不是 Provider）

| 占位点 | 位置 | 说明 / 后续替换 |
|---|---|---|
| 聚类 | `service/evolution/simple_cluster`（按 attribute_type 分组后再前后分半） | 换真实聚类，表不变 |
| patch 内容 | `service/evolution/patch.py` | 内容占位（追加小节），但**真实写文件、真实 commit**；后续换 LLM/规则生成 |
| eval / 终评 | `service/evolution/eval_gateway.py` + `eval_poller.py` | V1 可 `FakeEvalGateway`；真实接口走 submit/status/result 适配层；终评占位 |
| git 推送 | `HE_GIT_PUSH=true`（每轮 candidate 评测前） | candidate 推临时 ref → 评测 → 接纳后 fast-forward run 分支；失败进入 blocked，3 次立即 + 1/5/15min 退避 |

## 6. 错误模型与横切

统一错误响应（前端一个拦截器处理全部失败）：

```json
{ "error": { "code": "SESSION_NOT_FOUND", "message": "session 不存在", "details": {"session_id": "..."} } }
```

| 异常 | HTTP | code 前缀 |
|---|---|---|
| `NotFoundError` | 404 | `*_NOT_FOUND` |
| `ConflictError`（如重复同步冲突、run 已结束还推进） | 409 | `*_CONFLICT` |
| `ValidationError`（Pydantic 之外的手工校验） | 422 | `*_INVALID` |
| `AppError`（其他业务错误） | 400 | `*_ERROR` |
| 未捕获异常 | 500 | `INTERNAL`（响应不含堆栈，日志含 request_id） |

- 请求上下文：JWT 鉴权中间件把 `sub` 解析进 `RequestContext.principal`；公开端点仅 `/api/health` 与 `/api/auth/login`、`/api/auth/refresh`，其余一律要求登录。
- 日志：`structlog` 风格的结构化字段（`request_id / module / principal / duration_ms / code`），不打印轨迹原文（可能含敏感内容）。
- CORS：只允许配置的正式域名（`HE_CORS_ORIGINS`）；同源托管后可关闭。
- 限流（轻量）：登录端点按 IP 限速（如 10 次/分钟），防暴力破解；业务端点暂不限流（组织内部）。

## 7. 任务与进度

### 7.1 为什么不用 Celery

单实例 SaaS 下，任务是"秒级到分钟级的同步/聚类/推进"，且 V1 串行执行，不需要队列。设计上**接口先行**：`JobRunner` + `job_runs` 表 + 进程内串行 worker；未来并行/CI 时新增 executor 实现，业务代码不动。

### 7.2 `job_runs` 表 + 进程内串行 worker

```text
scheduler_loop()                                                # lifespan 启动；每 HE_SYNC_INTERVAL_SECONDS
  └─ pending 为 0 → 跳过
  └─ pending > 0 → trigger_sync(source="scheduler")（内部抢 sync_lock；抢不到跳过）

eval_poller_loop()                                              # lifespan 启动；每 30s 扫到期评测
  └─ round.eval_status=evaluating 且 eval_next_poll_at<=now
  └─ 每 HE_EVAL_POLL_SECONDS=300 调一次外部 status
  └─ completed → 入队 evolution_apply；failed/timeout → run blocked

blocked_sweeper_loop()                                         # lifespan 启动；每 30s 扫 blocked
  └─ next_retry_at<=now 且 retry_attempts<3
  └─ 入队 evolution_retry（自动退避每次只 push 1 次）

JobRunner.submit(kind, payload, ref_id, created_by) -> job_id   # 落 job_runs 行（status=queued），立刻返回
worker_loop()                                                   # lifespan 启动的串行执行器（V1 一把 asyncio.Lock）
  └─ 同一时刻只执行一个任务：claim → running → 更新 progress → completed/failed
  └─ 重启时把残留 running 标为 interrupted；可重试的 kind 重新入队
```

- **SQLite 与 MySQL 的差异**：V1 单实例串行，不依赖 `SKIP LOCKED`；未来多实例 worker 时用 MySQL `SELECT … FOR UPDATE SKIP LOCKED` 抢占，SQLite 只用于测试。
- **任务状态以 `job_runs` 表为准**：前端任何时候 `GET /api/jobs/{jobId}` 拿到的都是真值。
- **sync 单飞**：`sync_lock` 单行表 + TTL；scheduler 与手动触发共用。已有 sync 时手动请求返回现有 `jobId`（`reused=true`），不重复入队。
- **自进化任务**：`evolution_prepare` → `evolution_advance` →（eval_poller）→ `evolution_apply` → 下一轮 / `evolution_finalize`；`blocked` 时由 `blocked_sweeper` 或 `POST /retry` 入队 `evolution_retry`。
- 同一 run 只允许一个进行中的推进/重试任务，冲突抛 `RUN_BUSY`。
- **push 是评测前置条件**：每轮 candidate 先 push 到临时 candidate ref；失败进入 `blocked`，不提交评测。
- SSE 只是通知：run worker 推进时写 `job_runs.progress` 并 publish 事件；前端收到后失效 queryKey 重取。
- **sync 不经过 EventBus/SSE**：scheduler/manual 只写 `job_runs`，前端轮询 `GET /acquisition/status` / `GET /jobs/{id}`。
- `eval_poller` / `blocked_sweeper` 是轻量循环，不持有 JobRunner 全局锁；不要用 job 内 `asyncio.sleep(300)` 等评测。

### 7.3 SSE 事件总线

```text
evolution_advance ───► EventBus（内存 pub/sub，每 topic 一个 Queue 集合）
                                  │
                                  └──► SSE 连接 A（topic=run:evo-xxx）
```

- 没有 `sync` topic；同步状态从 `job_runs` / `/acquisition/status` 读。

事件类型（前端 `useRunEvents` 按 type 分发）：

| event | data | 触发 |
|---|---|---|
| `ping` | `{}` | 每 15s 心跳（防代理断流） |
| `run.event` | `{run_id, seq, event_type, level, stage}` | 执行事件追加 |
| `run.progress` | `{run_id, unit, total, status, stage_label}` | 自进化准备/推进/评测/重试 |
| `run.blocked` / `run.resumed` | `{run_id, stage, retry_attempts, next_retry_at}` | push/eval 阻塞与恢复 |
| `run.completed` | `{run_id, verdict}` | 终评完成 |
| `run.failed` / `run.interrupted` | `{run_id, stage, message, event_seq}` | 不可恢复失败/进程中断 |
| `reset` | `{run_id, reason}` | 事件游标失效，要求前端重拉快照 |

- SSE 端点：`GET /api/events?ticket=…`；topics 与 cursor 由 `POST /api/events/ticket` 绑定，URL 不再接受 topics。
- run 事件从 `evolution_run_events` 回放（首连 `lastEventId`，重连 `Last-Event-ID`）。
- **轨迹归一化（sync）没有 SSE**：进度走 `GET /acquisition/status` / `GET /jobs/{jobId}` 轮询。
- 只有 `preparing/running` 的 run 页面订阅；`blocked` 可继续轮询，终态关闭。

## 8. 扩展路径（单实例 SaaS → 多实例）

| 接缝 | 现在（单实例） | 扩展时改动面 |
|---|---|---|
| 身份 | 自建账号 + JWT，单组织共享 | 接 OIDC：加一个 OIDC 登录端点，principal 来源从 users 表换成 claims；业务代码不变 |
| 存储 | MySQL 8 主库；SQLite 仅测试 | 读写分离在 `Database` 适配器层加 read replica 路由；表结构不变 |
| 任务 | `job_runs` + 进程内串行 worker | worker 独立部署（同一 `job_runs` 表 `SKIP LOCKED` 抢占），或接 CI 平台：新增 executor 实现 |
| SSE | 内存事件总线 | 换 Redis pub/sub：`EventBus` 接口已抽象，业务无感 |
| 静态资源 | FastAPI `StaticFiles` | 换 nginx / CDN，无需改前端 |
| 多实例 | 不支持（内存总线 + 内存 worker 单进程） | 上三行完成后即可水平扩容 |

## 9. 配置项清单

| 变量 | 默认 | 说明 |
|---|---|---|
| `HE_HOST` / `HE_PORT` | `0.0.0.0` / `8787` | 监听地址 |
| `HE_DATA_DIR` | `./data` | SQLite 文件（测试用）与本地缓存目录（gitignore） |
| `HE_DB_DIALECT` | `mysql` | `mysql` / `sqlite`；生产 MySQL，测试 SQLite |
| `HE_DB_URL` | 空（按 dialect 推导） | 显式连接串；MySQL 示例见 §4.3 |
| `HE_DB_POOL_SIZE` / `HE_DB_MAX_OVERFLOW` | `10` / `20` | 仅 MySQL 生效 |
| `HE_DB_ECHO` | `false` | SQL 日志（调试用） |
| `HE_JWT_SECRET` | **必填** | access token 签名密钥（env 注入，不入库不入仓） |
| `HE_ACCESS_TOKEN_TTL_MIN` | `30` | access token 有效期 |
| `HE_REFRESH_TOKEN_TTL_DAYS` | `14` | refresh cookie 有效期 |
| `HE_ADMIN_USERNAME` / `HE_ADMIN_PASSWORD` | 空 | 首次启动且 users 为空时播种初始管理员 |
| `HE_PAYLOAD_TABLE` | `trajectory_payloads` | 外部脚本写入的原始 JSONL 表（只读） |
| `HE_UPSTREAM_BASE_URL` / `HE_UPSTREAM_TOKEN` | 空 | 上游轨迹查询接口（pull 用，上游实现后启用） |
| `HE_SYNC_INTERVAL_SECONDS` | `60` | 后台处理待归一化 payload 的间隔（0 = 关闭定时，仅 admin 手动） |
| `HE_WORKSPACE_DIR` | `data/workspaces` | 每次自进化 run 的独立工作区（git clone 目标） |
| `HE_GIT_PUSH` | `true` | 每轮 candidate 评测前 push；测试环境可设 false（此时不触发真实评测） |
| `HE_GIT_REMOTE` | `origin` | 推送远端名 |
| `HE_GIT_AUTHOR_NAME` / `HE_GIT_AUTHOR_EMAIL` | `harness-evolution` / `noreply@local` | commit author |
| `HE_EVAL_MODE` | `fake` | `fake` / `http`；V1 可先 fake，但 push 链路真实 |
| `HE_EVAL_BASE_URL` / `HE_EVAL_API_KEY` | 空 | 外部评测平台地址与密钥 |
| `HE_EVAL_POLL_SECONDS` | `300` | 评测状态轮询间隔（5 分钟） |
| `HE_EVAL_TIMEOUT_SECONDS` | `7200` | 单轮评测超时；超时后 run 进入 blocked |
| `HE_SSE_HEARTBEAT_SECONDS` | `15` | SSE 心跳 |
| `HE_LOG_LEVEL` | `info` | 日志级别 |
| `HE_CORS_ORIGINS` | `http://localhost:5173` | 允许的前端域名 |
| `HE_LLM_BASE_URL` / `HE_LLM_API_KEY` | 空 | **预留**，V1 不读取；密钥走环境变量，不入库 |

## 10. 测试策略

| 层 | 方式 | 重点 |
|---|---|---|
| 只读查询 | 单元/集成测试 | bad_case / probe 联表查询、状态合并、缺失字段降级 |
| 鉴权 | 单元 + 路由测试 | 登录/刷新/登出、错误密码 401、过期 token、SSE 票据一次性 |
| 同步 | 集成测试 | `trajectory_payloads` 待处理判定、幂等、payload 结构变更隔离 |
| 状态机 | 单元测试 | `evolution/state.py` 的 unit 推进规则（0..4+M+1）；越界推进报 409 |
| git workspace | 临时 git 仓库 + bare remote | clone tag、建分支、candidate commit、amend/reset、push、push 前分支校验 |
| Repository | 集成测试（参数化 SQLite / MySQL） | 幂等写入、聚合查询、事务边界；MySQL 用 `-m mysql` 标记 |
| 路由 | `httpx.AsyncClient(ASGITransport)` | 状态码、错误模型、分页、深链字段、未登录 401 |
| SSE | 测试客户端 | 票据 → 订阅 → 推进 → 收到事件 → 断开重连补发 |
| 契约 | `test_openapi.py` | 快照 OpenAPI 与 `packages/contracts` 生成物一致（CI 另跑 `pnpm contract:check`） |
