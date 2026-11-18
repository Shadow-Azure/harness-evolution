# 架构

[English](architecture.en.md) | 中文

记录服务边界、数据流与存储；切片理由见 `.agents/notes/`。

## 产品边界

含工作空间与成员、凭据上报、fixtures/本地导入、归一化、Agent 树、空间 Session 与总览、多归因错误详情、七步自进化与 lane DAG。V1 读端点与无空间路由处于兼容窗口，见 [compatibility.md](compatibility.md)。

## 服务划分

| 单元 | 技术 | 职责 |
|---|---|---|
| `apps/api` | Python 3.12 + FastAPI | HTTP API、服务编排、存储与外部数据边界 |
| `apps/web` | Vue 3 + Vite | 路由、公共数据层与渐进加载的业务页面 |
| `packages/contracts` | TypeScript | 前端共享协议与领域类型 |

路由只在 `apps/api/app/main.py` 注册；依赖方向为 `api → service → db/third_party_api`。

## 当前请求链路

```text
Web ──► middleware ──► public endpoints | bearer APIs | ticket-authenticated SSE → api routers
```

仅健康、登录、刷新、IdP 回调、票据 SSE 与凭据上报公开；其余走 Bearer JWT，建空间、用户管理、sync 与上游 pull 限全局管理员。access 30 分钟，refresh cookie 14 天且 httpOnly、SameSite=Strict，Secure 随协议（可用 `HE_COOKIE_SECURE` 覆盖）；鉴权与错误共用边界。

Web 先恢复 `auth/session` 再挂路由；token 与用户只留内存，401 单飞刷新，退出清 query cache。页面挂在 `/workspaces/:wid` 下，按 `wid` 与成员角色收口；`/`、`/sessions/**`、`/errors`、`/evolution/**` 重定向到记住的可见空间、唯一空间或选择页。

Session 页 360px 列表+概览，默认最新 10、回车查询；错误详情按 case 分组，深链 `case/tab/at`；对象配置与向导按空间，运行详情七步；lifespan 先恢复任务与 sync_lock 再调度。

轨迹未就绪不是 404。

## 数据层策略

- 生产 MySQL 8、本地/测试 SQLite；`HE_DB_DIALECT` 是唯一选择点。`Database` 统管连接、只读 session、写事务与 health；Alembic 维护双方言迁移，业务只依赖 `db/crud/` 与 `Database`。
- 空间：`workspaces`、`workspace_members`、`workspace_ingest_credentials`；bad case、对象配置与运行带 `workspace_id`。轨迹全局共享，空间 Session 由 bad case 投影。
- 上报：凭据只写 URL 空间，额度在写入事务内判定；同 ID 幂等 upsert，不重复计数。
- 归因：`bad_case_analysis` 以 `(bad_case_id, probe_id)` 关联多行；`probe_reports` 存结论、缓存键与复用计数；缓存键含空间、case、对象身份、版本、策略与引擎。
- 外部问题表按 06 §4 契约巡检：缺失表/列或类型漂移写 `external.contract_drift`，行级漂移汇总 `external.row_drift`；读失败映射为 `EXTERNAL_SCHEMA_DRIFT`/`EXTERNAL_READ_FORBIDDEN`/`EXTERNAL_READ_FAILED`，读路径只发 SELECT。
- 证据：父子关系分 `authoritative/derived/synthetic/unresolved`；`execution_outcome` 独立于解析；skill/agent/知识库文件匹配用归一化 body hash 或 tag；未知不猜名称。
- 知识触发：`kind=knowledge` 只认空间知识根或知识 Provider/Collection 返回的文档，存 `document_id`、revision、来源路径、检索方式与 tool_use，不存全文。
- 任务：`job_runs` 是任务真值，串行 worker 写 run 事件，总线有界通知；`sync_lock` 单飞，job 与锁同事务，异常 `sync_runs` 先终结再释放；原始 payload 按 `(runtime_key, root_session_id, agent_id)` 唯一保存，fixtures 幂等同构表，重放按 root 原子组装后事务重写。
- 上游用版本化 outbound contract；pull 先写 `http_api` payload 再共享重放；归一化由 `TraceParserFactory` 按 runtime 选子类，消息与内容不落库。
- 兼容：无前缀读端点按可见空间并集过滤；V1 run 只读映射七步；`bad_case_analysis.probe_id` 与 `probe_reports.cache_key` 可空。删除条件见 [compatibility.md](compatibility.md)。
- 密钥只从环境变量注入，不入仓库或数据库。

## 共享契约

FastAPI OpenAPI 是 inbound 唯一契约源；上游查询以严格 Pydantic 模型导出独立 JSON Schema 与 fixture，`contract:check` 防两类快照漂移。

健康响应让 API 与数据库状态分别可判：

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];
```

## 状态与边界

- 已具备：双库 API、鉴权与空间角色、凭据上报与额度、空间 Session 与总览、多归因错误详情、四步向导、七步运行与 lane DAG、证据门禁与知识触发、任务/SSE、对象配置、fixtures、跨栈 API/E2E 与文档/流程/契约门禁。
- 未具备：真实评测与 patch、用户停用界面。
- 明确不做：读生产密钥、无证据自动改代码、兼容窗口内删除 V1 面。
