# 16 · bad case 同步源工厂化：父类 + 工厂 + ClaudeUpstream 子类

> 本文回答：bad case 的 global 源线如何从「两个平级 HTTP 客户端 + 过程式装配 + 内联 if/else」收敛为「工厂按 .env 初始化子类，获取全部走父类模板方法、子类实现」；上报线与 global 线如何保持开关独立；已上报 bad case 如何不被目录同步覆盖；`_sync_root` 的两条取数路径如何合并为一个循环。
> 前置：[04 后端架构](04-backend-architecture.md) · [06 数据库设计](06-database-design.md) · [07 后端实现](07-backend-implementation.md) · [11 根会话轨迹定时同步](11-bad-case-session-sync.md) · [12 目录数据定时同步](12-bad-case-catalog-sync.md)。
> 状态：设计定稿（2026-11-23，issue #548 / bugfix-42，依据 main @ 2f4bce1d），待实现 issue 落地；实现冲突时以本文对应小节为准。决策记录见 Agent Note [`.agents/notes/implemented/architecture/2026-11-23-bad-case-sync-source-factory.md`](../../.agents/notes/implemented/architecture/2026-11-23-bad-case-sync-source-factory.md)。

<a id="s1"></a>
## 1. 现状盘点

bad case 有两条互相独立的来源线。下面按真实调用链列出每一跳的处理类与文件行号，作为 §2 差距判定与 §3 接口设计的证据基线。

### 1.1 上报线（report）· workspace 凭据

| 跳 | 做什么 | 位置 |
|---|---|---|
| 1 | `POST /api/workspaces/{wid}/bad-cases`，`Authorization: Bearer whk_…`；workspace 来自 URL，凭据必须属于它 | `apps/api/app/api/ingest.py` |
| 2 | `BadCaseIngestService.ingest` 校验 `sessionSource{runtime, sessionUrlTemplate}`（必须恰含一个 `{sessionId}`、绝对 http(s)、无凭据、无 fragment） | `apps/api/app/service/workspaces/ingest.py` |
| 3 | `BadCaseIngestRepository.ingest`：锁 workspace → 判定 id 归属（异 workspace → `BadCaseIdConflict`）→ 新插入计额度 / 同 workspace 重复上报替换 `_UPSTREAM_COLUMNS`（13 列，含 `session_source`） | `apps/api/app/db/crud/bad_case_ingest.py:24-38,158-200` |
| 4 | 同一事务内 `insert_pending_root`：insert-if-absent 一条 `pending` 的 root-sync 行；`synced` 吸收、`failed` 保留退避，除非重报带 `sessionSource` 且旧失败是确定性源错误才 re-arm | `apps/api/app/db/crud/bad_case_sync.py:212-270` |
| 5 | root 同步领取时 `latest_report_source` 取该 root 最新一条带 `sessionUrlTemplate` 的上报（按 `created_at desc, bad_case_id desc`），冻结为 `{"kind":"report", …}` 快照 | `db/crud/bad_case_sync.py:418-448` · `service/acquisition/bad_case_sync.py:255-268` |

### 1.2 global 源线 · 上游接口同步

| 跳 | 做什么 | 位置 |
|---|---|---|
| 1 | **目录分页**：`HttpBadCaseCatalogSource.fetch_page(after_id, offset, limit)` → `GET bad-cases?bad_case_id=&offset=&limit=`，进程级 `asyncio.Lock` 串行，`BadCasePage` 严格校验（有序、唯一、`total ≥ len`、回显 offset/limit、id > 游标） | `third_party_api/bad_case_query/http.py:16-155` · `models.py:40-78` |
| 2 | `BadCaseCatalogSyncService.run`：单行游标 `bad_case_catalog_sync`，按页提交；`max_id ≤ cursor` 即 `BAD_CASE_QUERY_INVALID_RESPONSE` | `service/acquisition/bad_case_catalog_sync.py:131-210` |
| 3 | `BadCaseCatalogSyncRepository.commit_page`：先 select 已存在 id，再 `INSERT … ON DUPLICATE KEY UPDATE`（SQLite `ON CONFLICT DO UPDATE`）对同 id 行**无条件**覆盖 `_UPDATE_COLUMNS`（13 列）；`updated = len(existing)` | `db/crud/bad_case_catalog_sync.py:24-38,228-274,295-305` |
| 4 | **两端点轨迹回填**：`HttpSessionQuerySource.list_children`（`GET sessions/{id}/children` → 裸数组）与 `fetch_trajectory`（`GET sessions/{id}/trajectory` → NDJSON → `canonicalize_body` → `SessionTrajectory{content, line_count}`） | `third_party_api/session_query/http.py:24-140` · `models.py:20-38` |
| 5 | `BadCaseRootSyncService._sync_global_root`：BFS 遍历，`_payload()` 组装 `LocalAgentPayload`，`runtime_key` 走 `LocalAgentPayload` 的默认值 `"claude-code"`（隐式硬编码），`agent_meta` 对子 agent 固定 `{"parentAgentId": parent}` | `service/acquisition/bad_case_sync.py:331-382,488-507` · `local_sessions.py:84-97` |

### 1.3 两条线在 root 同步处的汇合：`_sync_root` 的内联 if/else

每个 root 在**首次领取**时冻结来源选择（`_select_source` → `repository.claim(source_kind, source_snapshot)`），之后每次重试都复用冻结快照（`row["source_snapshot"] is None` 时才写入）。`_selection` 用 `SessionSourceSnapshot.model_validate`（`extra="forbid"`）校验快照并核对 `kind` 一致。随后 `_sync_root` 用 `if selection.kind == "report"` 在两个几乎同构的 BFS 循环间切换（`bad_case_sync.py:303-447`）：

| 路径 | 取数 | 落库 | 备注 |
|---|---|---|---|
| report · `_sync_report_root` | `SessionSourceFetcher.fetch(session_url_template, session_id, expected_parent_id, declared_runtime)` → `SessionInfo` | `_payload_from_info`（`runtime_key` 来自 `info.runtime_key`） | identity 校验在 `HttpSessionSourceClient._validate_identity`；运行时元数据由 `SessionSourceFactory.create(envelope.runtime)` 分派到 `BaseSessionSourceAdapter.project` |
| global · `_sync_global_root` | `SessionQuerySource.fetch_trajectory` + `list_children`（两个端点、无 envelope、无 runtime 声明） | `_payload()`（`runtime_key` 落 `LocalAgentPayload` 默认值） | 整条路径**不经过** `SessionSourceFactory` / `BaseSessionSourceAdapter`，与 report 路径的 `SessionInfo` 投影是两套并行实现 |

### 1.4 装配段：`main.py` 两段近似复制的过程式 if 块

| 行号 | 做什么 | 开关来源 | 问题 |
|---|---|---|---|
| `main.py:270-286` | `session_query_configured` 为真时建 `httpx.AsyncClient`（Bearer、超时）→ `HttpSessionQuerySource(client, max_retries, backoff)` | `Settings.session_query_configured`（`config.py:440-446`） | 客户端构造、鉴权头、重试参数、锁全部写在 composition root；两个客户端参数逐字重复 |
| `main.py:310-325` | `bad_case_query_configured` 为真时建另一个 `httpx.AsyncClient` → `HttpBadCaseCatalogSource` | `Settings.bad_case_query_configured`（`config.py:456-462`） | 同上 |
| `main.py:287-295` | 无条件构造 `HttpSessionSourceClient`（report 路径取数器） | 无开关 | report 路径的 fetcher 与 global 源的 fetcher 类型不同、签名不同，只能在 `_sync_root` 里 if/else |
| `main.py:296-338` | `BadCaseRootSyncService.from_settings(…, resolved_session_query_source, …, session_source_fetcher=…)`、两个 Coordinator、两个 `register_handler` | — | 服务同时持有 `SessionQuerySource \| None` 与 `SessionSourceFetcher \| None` 两个互不相干的取数依赖 |
| `main.py:686-703` | lifespan 逐个 `close()`：`resolved_session_query_source`、`resolved_catalog_source`、`session_source_http_client` | — | 关闭顺序手写在六层 `try/finally` 里，新增上游必须再加一层 |

**现状的一句话结论**：global 线没有一个「源」对象，它是 *两个 HTTP 客户端 + 一段装配代码 + 服务里两个私有方法* 的总和。「global」这个词在代码里只表示 **DB 快照标签**（`bad_case_root_sync.source_kind = "global"`）和 per-root 的路由状态，并不对应任何可替换的实现——这正是 §3 要补上的缺口。

<a id="s2"></a>
## 2. 差距分析

把用户特性诉求拆成七项目标要求，逐条对照 §1 的现状给出差距判定；每条的「收敛落点」指向 §3 的具体小节。

| # | 目标要求 | 现状（证据） | 判定 | 收敛落点 |
|---|---|---|---|---|
| R1 | global 线做成「工厂 + 父类 + 子类」 | `HttpBadCaseCatalogSource` 与 `HttpSessionQuerySource` 平级、互不相干；没有共同父类，没有工厂；装配靠 `main.py` 的 if 块（§1.4） | **缺口** | §3.1 新模块三件：`BaseBadCaseSyncSource` / `ClaudeUpstreamBadCaseSyncSource` / `BadCaseSyncSourceFactory` |
| R2 | bad case 获取与 session 获取全部走父类触发调用、子类实现 | `BadCaseCatalogSyncService` 直接依赖 `BadCaseCatalogSource` 协议；`BadCaseRootSyncService._sync_root` 用内联 if/else 在两条取数路径间切换（`bad_case_sync.py:303-447`），两套 BFS 循环重复 | **缺口** | §3.2 父类模板方法 `fetch_bad_case_page` / `fetch_session`；§3.4 「冻结快照 → 统一 fetcher」数据映射，单循环 |
| R3 | .env 配置后开启，未配置不开启 | 没有一个「global 线总开关」：启用与否由 `session_query_configured` / `bad_case_query_configured` 两个属性隐式决定，且在 `main.py`、两个 Coordinator 的 `available`、`_sync_global_root` 的 `source is None` 分支三处各自判断 | **缺口** | §3.5 `HE_BAD_CASE_SYNC_PROVIDER`：工厂在装配期读取一次；未配置 → 工厂返回 `None`，两半都「unavailable」 |
| R4 | 工厂按 .env 初始化子类 | `main.py:270-325` 两段近似复制的过程式 if 块手工 `new` 客户端与源 | **缺口** | §3.3 `BadCaseSyncSourceFactory.from_settings(settings)`；未知值启动失败（与 `GitPushProviderFactory` 同策略） |
| R5 | 所有相关改动封装在子类内 | HTTP 客户端构造、鉴权头、重试、锁在 `main.py` 与两个 `http.py`；payload 映射 `_payload()` 与 `runtime_key` 默认值在服务层与 `LocalAgentPayload` | **缺口** | §3.3 子类自带 `from_settings`、端点、重试、锁、envelope 合成；服务层只认 `SessionInfo` / `BadCasePage` |
| R6 | session 处理复用既有 Session 解析父类/子类，并新增子类实现 | report 路径走 `SessionSourceFactory.create(runtime)` → `BaseSessionSourceAdapter.project` → `SessionInfo`；global 路径完全绕开这条链，`runtime_key` 靠 `LocalAgentPayload` 默认值 `"claude-code"` 兜底（`local_sessions.py:97`） | **缺口** | §3.2 `fetch_session` 内部合成 `SessionSourceEnvelope` 并经既有 `SessionSourceFactory` 投影；新子类 `ClaudeUpstreamBadCaseSyncSource` 即「新增子类实现」，其它运行时按既有注册机制新增 `BaseSessionSourceAdapter` 子类 |
| R7 | 已上报 bad case 不重复同步（不被 global 覆盖） | 目录同步 `commit_page` 对已存在 id 无条件 `ON DUPLICATE KEY UPDATE` 覆盖 13 个上游列（含 `created_at`，而 `latest_report_source` 正按 `created_at desc` 排序）；且把它们全部计入 `updated`。`workspace_id` 与 `session_source` 虽不在覆盖列里，但 title/description/type/object/meta 都会被上游改写 | **缺口**（「一半意义」） | §3.6 写者归属：新增 `bad_cases.origin`（report / catalog），目录同步只更新自己拥有的行，其余计 `skipped` |

**判定汇总**：七项全部为「缺口」，但严重度不同：R1–R6 是结构性缺口（不改行为、可逐步迁移）；R7 是**数据正确性缺口**（已上报的标题/描述会被上游静默改写），应最先落地并可独立发布。§7.4 的实施顺序据此排列。

<a id="s3"></a>
## 3. 目标设计

新模块 `apps/api/app/third_party_api/bad_case_sync_source/` 三件：父类 `base.py`、子类 `claude_upstream.py`、工厂 `factory.py`。服务层（`service/acquisition/`）只依赖父类类型；`main.py` 只调用工厂。

### 3.1 类图与职责边界

```text
«ABC» BaseBadCaseSyncSource            ClaudeUpstreamBadCaseSyncSource        BadCaseSyncSourceFactory
  provider: ClassVar[str]                provider = "claude-upstream"            from_settings(settings) → Self | None
  模板方法（final，所有子类共享）：          封装全部上游差异：                         register(cls) → cls   # 装饰器，拒绝重复 provider
  + fetch_bad_case_page(...) → BadCasePage  + from_settings(settings) → Self    create(provider) → BaseBadCaseSyncSource
  + fetch_session(...) → SessionInfo          - _catalog: HttpBadCaseCatalogSource  provider_key(settings) → str | None
  抽象钩子（子类实现）：                        - _session: HttpSessionQuerySource
  # fetch_page(...) → BadCasePage             - _envelope: ClaudeUpstreamEnvelopeFactory
  # fetch_trajectory(id) → SessionTrajectory  # runtime_key() → "claude-code"
  # list_children(id) → tuple[str, ...]        端点、Bearer、超时、重试、退避、进程级锁、HTTP 客户端
  # build_envelope(...) → SessionSourceEnvelope  生命周期全部在子类内；外部看不到 httpx
  # close() → None
```

依赖方向：`service/acquisition` → `BaseBadCaseSyncSource`（类型）与 `SessionInfo` / `BadCasePage`（模型）；`main.py` → 工厂；子类 → 既有 `HttpBadCaseCatalogSource`、`HttpSessionQuerySource`、`SessionSourceFactory`。反向依赖为零。

### 3.2 父类接口：两个模板方法

**模板方法一 `fetch_bad_case_page`**：父类负责「调用触发 + 返回类型收敛」，子类的 `fetch_page` 负责端点与协议。`BadCaseCatalogSyncService` 的依赖类型从 `BadCaseCatalogSource | None` 改为 `BaseBadCaseSyncSource | None`，循环体不变。

```python
class BaseBadCaseSyncSource(ABC):
    """Parent for every bad-case sync source; template methods trigger, subclasses implement."""

    provider: ClassVar[str]

    async def fetch_bad_case_page(self, *, after_id: int, offset: int, limit: int) -> BadCasePage:
        """Template: one validated page with id greater than ``after_id``."""
        return await self.fetch_page(after_id=after_id, offset=offset, limit=limit)

    @abstractmethod
    async def fetch_page(self, *, after_id: int, offset: int, limit: int) -> BadCasePage: ...

    async def fetch_session(
        self,
        *,
        session_id: str,
        expected_parent_id: str | None,
        snapshot: SessionSourceSnapshot,
    ) -> SessionInfo:
        """Template: one runtime-agnostic session projection for root sync."""
        trajectory = await self.fetch_trajectory(session_id)
        children = await self.list_children(session_id)
        envelope = self.build_envelope(
            session_id=session_id,
            expected_parent_id=expected_parent_id,
            children=children,
            trajectory=trajectory,
        )
        return SessionSourceFactory.create(envelope.runtime).project(envelope, trajectory)

    @abstractmethod
    async def fetch_trajectory(self, session_id: str) -> SessionTrajectory: ...
    @abstractmethod
    async def list_children(self, session_id: str) -> tuple[str, ...]: ...
    @abstractmethod
    def build_envelope(self, *, session_id: str, expected_parent_id: str | None,
                       children: tuple[str, ...], trajectory: SessionTrajectory) -> SessionSourceEnvelope: ...
    @abstractmethod
    async def close(self) -> None: ...
```

父类把 `from_settings` 声明为抽象钩子（子类实现装配细节）；模板方法不加 `@final`——全仓没有该惯例，靠 ABC 与评审约束边界。

**签名对齐**：`fetch_session` 与既有 `SessionSourceFetcher.fetch(session_url_template=, session_id=, expected_parent_id=, declared_runtime=)` 同构——两者都接收 `session_id` + `expected_parent_id`，都返回 `SessionInfo`。差别只在第三个参数：report 路径需要 URL 模板，global 路径需要 provider；两者都来自**同一份冻结快照**，所以统一签名取 `snapshot: SessionSourceSnapshot`。

### 3.3 子类 `ClaudeUpstreamBadCaseSyncSource`：封装的全部内容

| 关注点 | 现状位置 | 目标：子类内部 |
|---|---|---|
| HTTP 客户端构造（base_url、Bearer、超时、`follow_redirects=False`） | `main.py:276-281`, `315-320` | `from_settings` 内部按 `HE_SESSION_QUERY_*` / `HE_BAD_CASE_QUERY_*` 建两个 `httpx.AsyncClient` |
| 重试次数、退避 | `main.py:284-285`, `323-324` | 子类读取同一组 settings，构造 `HttpBadCaseCatalogSource` / `HttpSessionQuerySource` |
| 进程级串行锁 | 两个 `http.py` 各自一把 | 不变（仍由两个 HTTP 实现持有），子类不暴露 |
| 运行时身份 | `LocalAgentPayload.runtime_key` 默认值 | 子类显式声明 `runtime_key = "claude-code"`，写入合成 envelope 的 `runtime` 字段；服务层不再依赖默认值 |
| envelope 合成（两端点 → `SessionSourceEnvelope`） | 不存在（`_payload()` 手工拼 `LocalAgentPayload`） | `ClaudeUpstreamEnvelopeFactory`：纯函数，`agentKind = "main" if expected_parent_id is None else "subagent"`，`parentSessionId = expected_parent_id`，`agentMeta = {}` |
| 生命周期 | `main.py:686-703` 六层 try/finally | 一个 `source.close()` 顺序关闭两个客户端；composition root 只多一层 |

合成 envelope 后，投影交给**既有**链路：`SessionSourceFactory.create("claude-code")` → `ClaudeCodeSessionSourceAdapter.project` → `SessionInfo`。对子 agent，`BaseSessionSourceAdapter.project` 会把 `parentSessionId` 合并为 `agentMeta.parentAgentId`；对 main agent，空 facts 得 `agent_meta=None`——与今天 `_payload()` 的产出**逐字段相同**（§5 Step 6 给出对照 JSON）。要支持新的运行时元数据，只需按既有机制新增一个 `BaseSessionSourceAdapter` 子类并注册新 runtime key，不改同步源父类。

### 3.4 决策 ④：`_sync_root` 收敛为「冻结快照 → 统一 fetcher」

现状：两个 if 分支、两套 BFS 循环。

```python
if selection.kind == "report":
    await self._sync_report_root(...)   # 循环 A：fetcher.fetch(...)
    return
await self._sync_global_root(...)       # 循环 B：source.fetch_trajectory + list_children
```

目标：一张映射表、一个循环。

```python
fetcher = self._fetcher_for(selection)   # {"report": ..., "global": ...}
while queue:
    info = await fetcher.fetch(
        session_id=session_id,
        expected_parent_id=parent_id,
        snapshot=selection,
    )
    self._write_payload(info)           # _payload_from_info
    self._enqueue_children(info.child_session_ids, ...)
```

映射表只有两项，都是数据而非控制流：`"report"` → `ReportSessionFetcher`（薄适配器，内部调既有 `SessionSourceFetcher.fetch(session_url_template=snapshot.session_url_template, …, declared_runtime=snapshot.runtime)`）；`"global"` → 装配期产出的 `BaseBadCaseSyncSource.fetch_session`（经 `GlobalSessionFetcher` 适配同一个 fetcher 签名）。快照里的 `provider` 参与一致性校验：与装配产物不一致即抛 `SESSION_SOURCE_INVALID_RESPONSE`（502），不会静默改道；源为 `None` 时与今天一样抛 `SESSION_QUERY_UNAVAILABLE`（503，在 `_NON_RETRYABLE_ERRORS` 内，配置出现后启动钩子 `reset_deterministic_failures` 会清快照 re-arm），错误码与重试语义完全保留。

### 3.5 决策 ②：两线独立与开关矩阵

global 线只有**一个**开关 `HE_BAD_CASE_SYNC_PROVIDER`（可选值：`claude-upstream`；空/未设置 = 关闭）。它**只被工厂在装配期（`create_app`）读取一次**，产出 `BaseBadCaseSyncSource | None` 注入两个服务；运行期没有任何代码再读这个环境变量。上报线没有 .env 开关：它随 API 可用而可用，由 workspace 凭据决定谁能写。「四种组合互不牵连」的含义是：任一开关状态下，另一条线的代码路径、数据写入与状态机完全相同。

| 上报线 | global 线 `HE_BAD_CASE_SYNC_PROVIDER` | bad_cases 来源 | root 同步来源路由（`_select_source`） | 状态接口 |
|---|---|---|---|---|
| 关（无 workspace 凭据） | 未设置 | 无 | 无候选；`_sources_available()` 为假，不提交 job | `sync.status = "unavailable"`，`catalog.status = "unavailable"` |
| 关 | `claude-upstream` | 仅目录同步（`origin = "catalog"`，默认 workspace） | 所有 root → `{"kind":"global","provider":"claude-upstream"}` | `idle / running / failed`；目录按游标推进 |
| 开（有凭据） | 未设置 | 仅上报 | 带 `sessionSource` 的 root → report 快照；不带的 root → `{"kind":"global"}`（无 provider）→ 领取后以 `SESSION_QUERY_UNAVAILABLE` 停车，配置出现后启动钩子 re-arm | 同上；目录 `unavailable` |
| 开 | `claude-upstream` | 两线并存；同 id 时按 `origin` 归属（§3.6） | 带 `sessionSource` → report；否则 → global（provider 冻结进快照） | `idle / running / failed` |

**兼容提醒（详见 §7.1）**：现网若已配置 `HE_SESSION_QUERY_*` / `HE_BAD_CASE_QUERY_*` 但未加 `HE_BAD_CASE_SYNC_PROVIDER`，升级后 global 线按「未配置不开启」语义关闭。工厂在装配期检测到「有端点凭据但无 provider」时打一条 warning，部署清单加一行即可恢复；不做隐式推断开启，否则「未配置不开启」就不再成立。

### 3.6 决策 ③：写者归属与跳过计数

**写者归属规则**：`bad_cases` 每行有一个写者 `origin ∈ {"report", "catalog"}`，由首次写入者决定，之后的更新只允许同一写者进行。上报线插入时写 `origin = "report"`（重报不改归属）；目录同步插入时写 `origin = "catalog"`，遇到已存在的 id 时只更新 `origin = "catalog"` 的行，`origin = "report"` 的行**跳过并计数**，不再有任何无条件覆盖。

```python
# db/crud/bad_case_catalog_sync.py（目标形态）
existing = {bad_case_id: origin for bad_case_id, origin in select(bad_cases.c.bad_case_id, bad_cases.c.origin).where(id.in_(ids))}
to_insert = [row for row in page if row.bad_case_id not in existing]           # origin = "catalog"
to_update = [row for row in page if existing.get(row.bad_case_id) == "catalog"]  # 只改自己拥有的
skipped   = [row for row in page if existing.get(row.bad_case_id) == "report"]   # 已上报：不动
# 同一事务：INSERT to_insert（保存点内失败 → 回滚保存点 → 重读真实 origin → catalog 行转 UPDATE、report 行计入 skipped）
#           UPDATE to_update SET _UPDATE_COLUMNS... WHERE bad_case_id IN (...) AND origin = "catalog"
#           推进游标 + synced_count + pending_count
return PageCounts(inserted=len(to_insert), updated=len(to_update), skipped=len(skipped))
```

`CatalogSyncResult` 与 job 结果映射新增 `skipped`；`BadCaseCatalogSyncStatus` 不加字段（避免动 `packages/contracts`；若产品需要「已上报被保护的数量」，由实现 issue 决定是否加 `skippedBadCases` 并 `pnpm contract:generate`）。跨方言说明：改为显式 `INSERT` + 条件 `UPDATE` 后不再需要 MySQL / SQLite 两套 upsert 语句，`_upsert_statement` 整体删除。

<a id="s4"></a>
## 4. 解耦推演

用四类上游变更场景检验 §3 的边界：每一类变更应当只落在一个文件集合内。改动局部性以「需要修改的文件数 / 是否触及服务层与 composition root」衡量。

| 场景 | 现状要改哪里 | 目标设计要改哪里 | 局部性 |
|---|---|---|---|
| **S1 新增一个上游**（另一家 bad case 目录 + session 接口） | 新建 2 个 HTTP 客户端类；`main.py` 再加两段 if 块；`BadCaseRootSyncService` 再加 `_sync_<x>_root` 第三套循环；`config.py` 加一组 `*_configured`；至少 4 个测试目录 | 新建 `bad_case_sync_source/<provider>.py` 一个子类并 `@BadCaseSyncSourceFactory.register`；`.env.example` 加可选值；`.env` 切 provider | **1 个新文件；服务层、main.py、DB 零改动** |
| **S2 上游协议变化**（目录加字段 / 鉴权方式变 / 端点路径变） | `bad_case_query/http.py`（或 `session_query/http.py`）+ `main.py` 的鉴权头与客户端参数 + `.env.example` | 子类内（端点、鉴权、客户端参数）；若契约模型变，`BadCaseItem` 随之 | **子类 + 模型；composition root 不感知** |
| **S3 配置形态变化**（例如某上游需要 per-provider 的端点变量名、或要改为双实例） | `config.py` + `main.py` 两处同步改，且两个 Coordinator 的 `available` 判断也要改 | 子类 `from_settings` 自己解释 settings；工厂只看 `HE_BAD_CASE_SYNC_PROVIDER` | **子类单点；`available` 统一为「工厂产物是否为 None」** |
| **S4 遍历/持久化策略变化**（深度、agent 上限、租约、重试阶梯、replay 触发） | `BadCaseRootSyncService` + repository | 不变：仍在 `BadCaseRootSyncService` / `BadCaseRootSyncRepository`；子类不感知遍历 | **边界清晰：子类负责「取」，服务负责「走与存」** |

**解耦的判据**：父类接口只暴露两个动作（取一页目录、取一个 session 投影）和两种返回类型（`BadCasePage`、`SessionInfo`），两者都是**已经存在**的运行时无关模型。任何上游差异，只要能被表达为「如何产出这两种对象」，就能被封装在子类内；反之，若某项差异需要改变遍历或落库语义，它本来就不属于「源」，不应进子类。

<a id="s5"></a>
## 5. 目录同步数据流：逐步 JSON 对照

链路：`fetch_bad_case_page` → `BadCasePage` → `CatalogCaseRow` → 写者归属分流（插入 / 更新自有 / 跳过已上报）→ 落库并推进游标。每步给出处理类.函数与输入/输出 JSON 形态；示例游标 `1200`，页大小 200。

### Step 1 · `BadCaseCatalogSyncService.run` → `BaseBadCaseSyncSource.fetch_bad_case_page`（模板方法）

读取单行游标状态，按 `max_pages` / 时间预算循环；每页调用父类模板方法，子类 `ClaudeUpstreamBadCaseSyncSource.fetch_page` 触发 `HttpBadCaseCatalogSource.fetch_page`。

```text
输入（调用参数）                         HTTP 请求（子类内部）
{"after_id": 1200, "offset": 0, "limit": 200}
                                        GET {HE_BAD_CASE_QUERY_BASE_URL}/bad-cases?bad_case_id=1200&offset=0&limit=200
                                        Authorization: Bearer •••   Accept: application/json
```

### Step 2 · 上游原始响应（纯 JSON）

字段名与本地 `bad_cases` 列对齐；`bad_case_title` / `bad_case_description` 是别名。

```json
{
  "total": 1203,
  "offset": 0,
  "limit": 200,
  "items": [
    {
      "bad_case_id": 1201,
      "bad_case_session_id": "01JROOTAAAAAAAAAAAAAAAA",
      "bad_case_type": "skill",
      "object_name": "code_review",
      "object_type": "skill",
      "object_version": "v3",
      "bad_case_agent_id": "reviewer-1",
      "trigger_line": 42,
      "bad_case_title": "Review missed a breaking change",
      "bad_case_description": "…",
      "meta_data": {"lane": "code-review"},
      "source": "code_reivew",
      "created_at": "2026-11-23T10:00:00+08:00",
      "updated_at": "2026-11-23T10:05:00+08:00"
    }
  ]
}
```

### Step 3 · `HttpBadCaseCatalogSource._parse` → `BadCasePage.model_validate`

`extra="forbid"`；别名映射为 `title` / `description`；校验 items 不超 limit、按 id 升序、不重复、`total ≥ len(items)`、回显 offset/limit、所有 id > `after_id`；时间戳必须带时区。

```text
输出：BadCasePage（校验后）                 失败形态（AppError 502）
BadCasePage(                                code = BAD_CASE_QUERY_INVALID_RESPONSE
  total=1203, offset=0, limit=200,          message ∈ {
  items=(BadCaseItem(                        "page response was not JSON",
    bad_case_id=1201,                        "page response did not match the contract",
    bad_case_session_id="01JROOTAAAAAAAAAAAAAAAA",
    bad_case_type="skill",                   "page response did not echo the requested offset and limit",
    object_name="code_review",               "page returned an id at or below the cursor",
    object_type="skill",                   }
    object_version="v3",
    bad_case_agent_id="reviewer-1",
    trigger_line=42,
    title="Review missed a breaking change",
    description="…",
    meta_data={"lane": "code-review"},
    source="code_reivew",
    created_at=2026-11-23T10:00:00+08:00,
    updated_at=2026-11-23T10:05:00+08:00,
  ),)
)
```

### Step 4 · `BadCaseCatalogSyncService._row(item, page_now)` → `CatalogCaseRow`

映射到本地列名：`object_name` 为空时走 `_SOURCE_OBJECT_NAMES`（`code_reivew`/`code_review` → `code-review`）或 `source` 或 `"unknown"`；`object_type` 缺省 `"skill"`；`created_at`/`updated_at` 缺省为 `page_now`。`max_id = items[-1].bad_case_id`，`max_id ≤ cursor` 则失败。

```text
输出：CatalogCaseRow                          页面派生量
CatalogCaseRow(
  bad_case_id=1201,                           {"max_id": 1201, "remaining": 1003,  # total - len(items)
  bad_case_session_id="01JROOTAAAAAAAAAAAAAAAA", "cursor_next": 1201}
  bad_case_type="skill",
  object_name="code-review",          # 别名归一
  object_type="skill",
  object_version="v3",
  bad_case_agent_id="reviewer-1",
  trigger_line=42,
  title="Review missed a breaking change",
  description="…",
  meta_data={"lane": "code-review"},
  source="code_reivew",
  created_at=2026-11-23T10:00:00+08:00,
  updated_at=2026-11-23T10:05:00+08:00,
)
```

### Step 5 · `BadCaseCatalogSyncRepository.commit_page(rows, last_bad_case_id, pending_count, now)`：写者归属分流

同一事务内：读已存在 id 的 `origin` → 三分流 → `INSERT to_insert`（`origin="catalog"`，`workspace_id` 落默认 workspace）→ `UPDATE to_update … WHERE origin="catalog"` → 推进游标。示例页含 3 条：1201 新 id、1202 是目录自有行、1203 已被某 workspace 上报。

```text
输入：页面行 + 已存在归属                     输出：PageCounts（新增 skipped）
rows    = [1201, 1202, 1203]                 PageCounts(inserted=1, updated=1, skipped=1)
existing = {                                # 现状对照：UpsertCounts(inserted=1, updated=2)  ← 1203 被覆盖且计为 updated
  "1202": "catalog",   # 上一轮目录同步写入
  "1203": "report",    # workspace 凭据上报，带 session_source
}
```

```text
bad_cases 行 · 1201（INSERT）                 bad_cases 行 · 1203（保持不变）
{"bad_case_id": "1201", "workspace_id": "default", "origin": "catalog",
 "bad_case_session_id": "01JROOTAAAAAAAAAAAAAAAA", "bad_case_type": "skill",
 "object_name": "code-review", "object_type": "skill", "object_version": "v3",      {"bad_case_id": "1203", "workspace_id": "ws-7f…", "origin": "report",
 "bad_case_agent_id": "reviewer-1", "trigger_line": 42,                                 "title": "上报时的标题",
 "title": "Review missed a breaking change", "bad_case_description": "…",              "session_source": {"runtime": "claude-code", "sessionUrlTemplate": "https://…/{sessionId}"},
 "meta_data": {"lane": "code-review"}, "source": "code_reivew", "session_source": null, "created_at": "2026-11-22T18:30:00+08:00",   # 不再被上游 created_at 改写
 "created_at": "2026-11-23T10:00:00+08:00", "updated_at": "2026-11-23T10:05:00+08:00"}   …}
```

### Step 6 · 游标行 `bad_case_catalog_sync` 与结果

游标只前进；页内 `len(items) ≥ total` 或空页即 `exhausted`；异常 → `mark_failed(_stable_error(exc))` 后重抛。

```text
游标行（同事务更新）                           job 结果映射（handle）
{"id": "bad_cases", "last_bad_case_id": 1201, "synced_count": 1188,
 "pending_count": 1003, "status": "running", "attempts": 0,                {"pages": 1, "inserted": 1, "updated": 1, "skipped": 1,
 "last_error": null, "last_run_at": "…", "last_success_at": null}           "lastBadCaseId": 1201, "pending": 1003, "exhausted": false}
```

<a id="s6"></a>
## 6. root 同步数据流：逐步 JSON 对照

链路：候选 → 源路由与冻结 → 领取 → 快照校验 → 统一 fetcher 取 `SessionInfo` → payload → 落库 → replay 解析 → 标记完成。以 global 路径为主线，report 路径在 Step 6 给出等价形态。

### Step 1 · `BadCaseRootSyncService.run` → `BadCaseRootSyncRepository.list_candidates(now, limit=20)`

候选 = 无状态行的 root ∪ pending ∪ 到期可重试的 failed ∪ 租约过期的 syncing；确定性失败（`_NON_RETRYABLE_ERRORS`）不进候选。

```text
输入                                        输出
{"now": "2026-11-23T22:00:00+08:00", "limit": 20}    ["01JROOTAAAAAAAAAAAAAAAA"]
```

### Step 2 · `_select_source(root_session_id)` → `(source_kind, source_snapshot)`

顺序：已冻结的快照原样复用 → 有过尝试（`attempts > 0`）则 global → 最新带 `sessionUrlTemplate` 的上报则 report → 否则 global。**新增**：global 分支把工厂当前 provider 盖进快照；未配置时保持今天的 `{"kind": "global"}`。

```text
输出 · 有上报源                               输出 · global（provider 已配置）
("report", {                                 ("global", {"kind": "global", "provider": "claude-upstream"})
  "kind": "report",                          # 未配置时：("global", {"kind": "global"})   ← 与现状逐字节相同
  "runtime": "claude-code",                      # 上报声明，可空
  "session_url_template": "https://reports.example.com/s/{sessionId}"
})
```

### Step 3 · `BadCaseRootSyncRepository.claim(root, owner, lease_seconds, now, source_kind, source_snapshot)`

`SELECT … FOR UPDATE`；`synced` 拒绝、租约未过期拒绝、退避未到期拒绝；`source_snapshot IS NULL` 时才写入快照（首次冻结）。

```text
bad_case_root_sync 行（冻结后）               输出
{"root_session_id": "01JROOTAAAAAAAAAAAAAAAA", "status": "syncing",    True   # 领取成功；False → roots_skipped += 1
 "source_kind": "global",
 "source_snapshot": {"kind": "global", "provider": "claude-upstream"},
 "attempts": 1, "last_error": null, "agent_count": 0,
 "lease_owner": "job-01J…", "lease_expires_at": "2026-11-23T22:15:00+08:00"}
```

### Step 4 · `_selection(state)` → `SessionSourceSnapshot.model_validate(state.source_snapshot)`

`extra="forbid"`；`kind` 必须与 `source_kind` 一致；report 必须有模板；global 不得带模板/运行时。**扩展**：新增可选 `provider`（仅 global 允许）。旧快照 `{"kind":"global"}` 仍合法。

```text
输出：SessionSourceSnapshot                   校验器（目标）
SessionSourceSnapshot(kind="global", provider="claude-upstream",
                      runtime=None, session_url_template=None)    report  → session_url_template 必填；provider 必须为 None
                                                                 global  → session_url_template / runtime 必须为 None；provider 可选
                                                                 不一致  → AppError(502, SESSION_SOURCE_INVALID_RESPONSE)
```

### Step 5 · `_sync_root`：冻结快照 → 统一 fetcher（数据映射）

不再有 if/else 分支体，只有一张映射；两种 fetcher 签名一致。

```text
映射                                         统一签名（Protocol）
{"report": ReportSessionFetcher(self._session_source_fetcher),
 "global": self._bad_case_sync_source.fetch_session}    async def fetch(*, session_id: str,
                                                                         expected_parent_id: str | None,
                                                                         snapshot: SessionSourceSnapshot) -> SessionInfo
```

### Step 6 · global：`ClaudeUpstreamBadCaseSyncSource.fetch_session`

父类模板依次触发子类两个端点，再由子类 `build_envelope` 合成 envelope，最后交**既有** `SessionSourceFactory.create("claude-code").project` 投影。

```text
6a · list_children                           6b · fetch_trajectory
GET …/sessions/01JROOTAAAAAAAAAAAAAAAA/children    GET …/sessions/01JROOTAAAAAAAAAAAAAAAA/trajectory
→ ["01JCHILDBBBBBBBBBBBBBBBB"]               Accept: application/x-ndjson
                                             → canonicalize_body(body)
                                             → SessionTrajectory(content="…", line_count=128)
```

6c · 合成 `SessionSourceEnvelope`（camelCase，`extra="forbid"`）：

```json
{
  "schemaVersion": 1,
  "sessionId": "01JROOTAAAAAAAAAAAAAAAA",
  "runtime": "claude-code",
  "runtimeVersion": null,
  "agentKind": "main",
  "parentSessionId": null,
  "childSessionIds": ["01JCHILDBBBBBBBBBBBBBBBB"],
  "agentMeta": {},
  "trajectory": {"format": "ndjson", "lineCount": 128, "content": "…"},
  "updatedAt": null
}
```

`runtime` 由子类显式声明，不再依赖 `LocalAgentPayload` 默认值；`agentKind` 取 `expected_parent_id is None`。

```text
输出：SessionInfo（两路径同形）                 Step 6 · report 等价形态
SessionInfo(                                  HttpSessionSourceClient.fetch(
  runtime_key="claude-code",                    session_url_template=snapshot.session_url_template,
  agent_kind="main",                            session_id="01JROOTAAAAAAAAAAAAAAAA",
  parent_agent_id=None,                         expected_parent_id=None,
  child_session_ids=("01JCHILDBBBBBBBBBBBBBBBB",),   declared_runtime=snapshot.runtime,
  agent_meta=None,           # main + 空 facts → None   ) → 同一个 SessionSourceEnvelope → 同一个 SessionInfo
  trajectory=SessionTrajectory(content="…", line_count=128),
  runtime_version=None,
)
```

子 agent（`expected_parent_id="01JROOT…"`）时 envelope 为 `agentKind="subagent"`、`parentSessionId="01JROOT…"`，投影后 `agent_meta={"parentAgentId": "01JROOT…"}`——与现状 `_payload()` 的产出逐字段相同。

### Step 7 · `_payload_from_info(root_session_id, session_id, info, now)` → `LocalAgentPayload`

唯一保留的 payload 映射函数；`_payload()` 删除。`runtime_key` 取 `info.runtime_key`。

```json
{"root_session_id": "01JROOTAAAAAAAAAAAAAAAA", "agent_id": "01JROOTAAAAAAAAAAAAAAAA",
 "agent_kind": "main", "content": "…", "content_hash": "sha256:…", "line_count": 128,
 "agent_meta": null, "source_updated_at": "2026-11-23T22:00:01+08:00",
 "discovered_at": "2026-11-23T22:00:01+08:00", "runtime_key": "claude-code"}
```

### Step 8 · `write_local_payloads(db, (payload,), source_type="http_api")` → `renew_lease` → `_enqueue_children`

按 `(runtime_key, root_session_id, agent_id)` 幂等 upsert 到 `local_agent_payloads`；每个 agent 写完续租；子节点去重入队，超过 `max_depth` 抛 `TRAVERSAL_LIMIT_EXCEEDED`。循环推进到子 agent 时 Step 6–8 以 `expected_parent_id="01JROOT…"` 重复。

```text
输出：LocalImportResult（节选）                 RootSyncProgress
LocalImportResult(status="imported", inserted_payloads=1, updated_payloads=0, …)    {"agent_count": 1, "inserted": 1, "updated": 0}
```

### Step 9 · 批末 `replay_pending_payloads(db, source_type="http_api", sync_run_id)`

按 `(runtime_key, root_session_id)` 分组，`TraceParserFactory.for_trace(payloads)` 选解析器（`claude-code` → `ClaudeCodeTraceParser`），产出 `session_families` / agents / messages；`runtime_key` 不在注册表 → `UNSUPPORTED_RUNTIME`（确定性失败）。这一步完全复用既有解析链，是「session 处理复用既有父类/子类」的落点。

```text
ReplayResult（聚合）                           随后 mark_synced
{"imported": 1, "skipped": 0, "failed": 0}    {"status": "synced", "agent_count": 1, "last_error": null,
                                               "synced_at": "2026-11-23T22:00:02+08:00", "lease_owner": null}
```

<a id="s7"></a>
## 7. 兼容与风险

本设计不改任何接口契约与 job kind；行为变化只有三处且都可控：payload 映射等价替换、目录同步不再覆盖已上报行、global 线需要一个显式开关。下面按风险逐条给出兼容面、暴露面与缓解。

### 7.1 `SessionSourceSnapshot` 扩展（`extra="forbid"`）

| 方向 | 情形 | 结果 | 缓解 |
|---|---|---|---|
| 新代码读旧行 | DB 里冻结的 `{"kind":"global"}` / `{"kind":"report",…}` | **合法**：`provider` 可选，默认 `None`（= 领取时未配置 provider；路由到工厂当前产物） | 无需迁移 |
| 旧代码读新行（回滚） | 冻结的 `{"kind":"global","provider":"claude-upstream"}` | `extra="forbid"` 拒绝 → `SESSION_SOURCE_INVALID_RESPONSE`（502，不在 `_NON_RETRYABLE_ERRORS`，按 1m/5m/15m/1h 阶梯重试且每次重试仍被拒） | 回滚后手工清理该 root 的 `source_snapshot`；启动钩子只清确定性失败集合内的行，不清这一类 |
| 校验器变更 | report 快照带 `provider`；global 快照带模板/运行时 | **一律拒绝**（report 不允许 provider；global 不允许模板与运行时，规则不变） | 单测覆盖三种非法组合 |

### 7.2 行为兼容清单

| 关注点 | 现状 | 目标 | 兼容判定 |
|---|---|---|---|
| payload 字段 | `_payload()`：main → `agent_meta=None`；subagent → `{"parentAgentId": parent}`；`runtime_key="claude-code"` | 合成 envelope → 既有投影 → 同值 | **逐字段相同**（加 parity 测试锁定） |
| 错误码 | 源未配置 → `SESSION_QUERY_UNAVAILABLE`（503，不可重试）；目录未配置 → `BAD_CASE_QUERY_UNAVAILABLE` | 工厂产物为 `None` 时抛同一错误码 | **不变**；`_NON_RETRYABLE_ERRORS` 不改 |
| job kind / 调度 | `bad_case_root_sync`、`bad_case_catalog_sync`；单飞 + 周期 | 不变 | **不变** |
| 状态接口 | `sync.status="unavailable"` 当无任何源 | `available` = 「工厂产物非 `None` 或存在 report 源」 | **语义不变** |
| job 结果 | 目录：`{pages, inserted, updated, lastBadCaseId, pending, exhausted}` | 新增 `skipped` | 增量字段；job 结果不在 OpenAPI 严格 schema 内 |
| 目录覆盖语义 | 同 id 无条件覆盖 13 列 | 只覆盖 `origin="catalog"` 的行 | **有意的行为变化**：已上报行受保护 |
| global 线开关 | 由两组端点凭据隐式开启 | `HE_BAD_CASE_SYNC_PROVIDER` 显式开启 | **有意的运维变化**：现网需加一行；装配期 warning 提示 |
| 注入缝 | `create_app(session_query_source=…, bad_case_catalog_source=…)` | 收敛为 `create_app(bad_case_sync_source=…)`；`session_source_fetcher=` 保留 | 测试夹具需改名（§7.3） |

### 7.3 测试影响面

| 测试目录 / 文件 | 影响 | 动作 |
|---|---|---|
| `tests/m6-16-bad-case-catalog-sync/`（query client / service / repository / coordinator / status / config / migration） | service 依赖类型改父类；repository 新增三分流与 `skipped`；migration 多一条 `origin` | 改夹具为 `BaseBadCaseSyncSource` 假实现；新增「已上报行被跳过且计数」「IntegrityError 归入 skipped」「origin 回填」用例 |
| `tests/m6-15-bad-case-session-sync/`（service / repository / coordinator / parent fallback / query client / status） | `_sync_root` 单循环；global 源经 `fetch_session`；快照带 provider | 新增 parity 测试：同一输入下 `_payload()`（旧，测试内保留参照实现）与 `fetch_session → _payload_from_info` 产出相等；补 provider 冻结 / 未配置停车 / 回滚快照被拒三例 |
| `tests/m9-07-report-session-source/`（source selection / ingest / client） | report 路径改经 `ReportSessionFetcher` | 断言不变；加一例「report 快照带 provider 被拒」 |
| `tests/test_app.py` 及所有调用 `create_app(session_query_source=…)` 的夹具 | 注入缝改名 | 机械替换为 `bad_case_sync_source=FakeBadCaseSyncSource(…)` |
| 新增 `tests/bugfix-42-bad-case-sync-source-factory/` | 工厂与子类 | 未配置 → `None`；未知 provider → 启动失败；重复 register → 失败；子类 `close()` 关闭两个客户端；envelope 合成对 main/subagent 两形态 |

### 7.4 实施顺序（供实现 issue 切分）

1. **数据正确性优先**：迁移加 `bad_cases.origin`（`report` / `catalog`），回填规则：`workspace_id ≠ DEFAULT_WORKSPACE_ID` 或 `session_source IS NOT NULL` → `report`，否则 `catalog`；目录同步改为三分流 + `skipped`。游标式同步只取 `id > cursor` 的页，历史行几乎不会被再次触碰，回填误差的实际暴露面接近零。可独立发布。
2. **新模块落地但不接线**：`bad_case_sync_source/` 三件 + parity 测试；`main.py` 仍走旧装配。
3. **快照扩展与单循环**：`SessionSourceSnapshot.provider`；`_select_source` 盖 provider；`_sync_root` 改映射 + 单循环；删除 `_payload()`。
4. **装配切换**：`create_app(bad_case_sync_source=BadCaseSyncSourceFactory.from_settings(settings))`；lifespan 只关一个源 + report fetcher 客户端；删 `session_query_source=` / `bad_case_catalog_source=` 注入缝；装配期 warning「有端点凭据但无 provider」。
5. **配置与文档**：`.env.example` 增 `HE_BAD_CASE_SYNC_PROVIDER`（注释写明「未设置 = global 线关闭」）；部署清单加一行；`docs/architecture.md` 的 acquisition 小节补「同步源 = 工厂产物」一句；[12 章](12-bad-case-catalog-sync.md) §4.3「已存在记录的更新」与 §5.1「方言实现」按本文 §3.6 修订。

**本设计不裁决的事项**：实现 issue 的切分粒度与排期；是否为状态接口增加 `skippedBadCases`（涉及 `packages/contracts`）；是否在工厂层支持多 provider 并存（当前决策：单部署单 provider，与 `GitPushProviderFactory` 一致）；`kind="global"` 这一 DB 标签是否改名（当前决策：不动）。
