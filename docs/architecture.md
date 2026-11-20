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

健康、登录、刷新、IdP 回调、票据 SSE 与凭据上报公开；其余走 Bearer JWT，全局写入口限管理员。access 30 分钟；refresh cookie 14 天，httpOnly、SameSite=Strict，Secure 随协议或配置；鉴权错误共用边界。

Web 先恢复 `auth/session`；身份留内存，401 单飞刷新，退出清缓存。页面在 `/workspaces/:wid` 下按空间与角色收口；无空间路由重定向到记住的空间、唯一空间或选择页。

Session 默认最新 10 条并回车搜索；错误按 case 分组并支持 `case/tab/at` 深链；对象与向导按空间，七步 Run 展示固化 revision；lifespan 恢复任务与 `sync_lock` 后调度。

轨迹未就绪不是 404。

## 数据层策略

- 生产 MySQL 8、本地/测试 SQLite；`HE_DB_DIALECT` 是唯一选择点。`Database` 统管连接、只读 session、写事务与 health；Alembic 维护双方言迁移，业务只依赖 `db/crud/` 与 `Database`。
- 空间：`workspaces`、`workspace_members`、`workspace_ingest_credentials`；bad case、对象配置与运行带 `workspace_id`。轨迹全局共享，空间 Session 由 bad case 投影。
- 上报：凭据只写 URL 空间，额度在写入事务内判定；同 ID 幂等 upsert，不重复计数。
- 对象绑定一个空间 Skill，默认 `attribute-badcases`。保存绑定触发独立后台归因。向导按对象版本逐 Badcase 复用最新报告，或选择 Skill 单次重算。`HE_ATTRIBUTION_AGENT=claude` 启用本地 CLI，`HE_ATTRIBUTION_MODEL` 选择模型。空间下的 `attribute_skill` 存包，`attribute_source` 存对象定义，`attribute_output` 存逐 Badcase 报告。Worker 校验平台脚本输出，将原始报告随 V2 写入 `probe_reports` 并在同一事务关联候选。
- 外部问题表按 06 §4 巡检；schema/行漂移写结构化日志，读失败映射为稳定错误码，读路径只发 SELECT。
- 证据：父子关系分 `authoritative/derived/synthetic/unresolved`；`execution_outcome` 独立于解析状态；对象 revision 取 `path + body hash` 或 tag，未知 revision 不按名称猜测。
- 知识触发：`kind=knowledge` 只认空间知识根或 Provider/Collection 文档，存身份、revision、来源与检索证据，不存全文。
- 任务：`job_runs` 是真值；默认串行，归因走 claim/lease 有界 lane，四入口共享幂等服务。`sync_lock` 与 job 同事务单飞；payload 三元组唯一，重放按 root 原子重写。
- 上游用版本化 outbound contract；pull 先写 `http_api` payload 再共享重放；归一化由 `TraceParserFactory` 按 runtime 选子类，消息与内容不落库。
- 兼容：无前缀读取可见空间并集；V1 run 只读映射七步；遗留可空字段与删除条件见 [compatibility.md](compatibility.md)。
- 密钥只从环境变量注入，不入仓库或数据库。

## 共享契约

FastAPI OpenAPI 是 inbound 唯一契约源；上游查询以严格 Pydantic 模型导出独立 JSON Schema 与 fixture，`contract:check` 防两类快照漂移。

健康响应让 API 与数据库状态分别可判：

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];
```

## 状态与边界

- 已具备：API、鉴权与空间角色、凭据上报与额度、空间 Session 与总览、多归因错误详情、四步向导、七步运行与 lane DAG、证据门禁与知识触发、任务/SSE、对象配置、fixtures、跨栈 API/E2E 与文档/流程/契约门禁。
- 未具备：真实评测与 patch、用户停用界面。
- 明确不做：读生产密钥、无证据自动改代码、兼容窗口内删除 V1 面。
