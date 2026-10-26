# 架构

[English](architecture.en.md) | 中文

记录服务边界、数据流与存储；按垂直切片实现，理由见 `.agents/notes/`。

## 产品边界

含 fixture、本地导入、归一化、树组装与会话查询。

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

仅健康、登录、刷新和票据 SSE 公开；其余 API 需 Bearer JWT，用户管理、手动 sync 与上游 pull 仅管理员。access 30 分钟，refresh cookie 14 天且 httpOnly、SameSite=Strict；登录限流，强改密只放行必要端点，错误共用 envelope。

Web 先恢复会话再挂载路由；token 与用户只留内存。守卫处理登录和强改密；并发 401 单飞刷新并各重放一次；退出清 query cache。

Session 页用 360px 列表+概览；搜索/状态/排序/选中/证据写 URL，统计/密度读 `/api/sessions`。

列表与概览分别记忆每个 Session 的滚动位置；刷新重置。流图按需异步加载。入口与 vendor 体积由 `verify:bundle` 守门，合成 61-Agent 真实浏览器预算由 `performance:report` 复测。

lifespan 先恢复 JobRunner 并采纳 `sync_lock`，再启动 scheduler；手动与定时共用单飞锁，无 pending 不建 job。

## 数据层策略

- 生产数据库目标为 MySQL 8，本地快跑与自动化测试使用 SQLite；`HE_DB_DIALECT` 是唯一选择点。
- `Database` 统一连接、只读 session、写事务和 health。
- Alembic 维护一棵双方言迁移树，SQLite 变更使用 batch 模式；业务代码只依赖 `db/crud/` repository 与 `Database` 接口，不直接拼接 SQL。
- `job_runs` 是任务真值；串行 worker 写 run 事件，事件总线只做有界通知。
- `sync_lock` 是单飞真值，默认 TTL 30 分钟；job 与锁同事务创建，terminal hook 先终结异常 `sync_runs` 再释放匹配锁。
- 原始 payload 按 `(root_session_id, agent_id)` 唯一保存；fixtures 通过 CLI 幂等写同构表。
- 上游查询使用独立版本化 outbound contract；pull 以 `http_api` 来源先写原始 payload 再共享重放。缺配置不可用，CI 只用 mock。
- 归一化按 payload 独立解析，消息与内容块只在内存中存在；输出用户输入锚点、Agent/Skill/Workflow 触发点和统计。
- 重放按 root 原子执行：先解析/组装，再事务重写并推进 source 游标。
- 问题和归因由外部系统写入，服务只读。
- 密钥只从环境变量注入，不入仓库或数据库。

## 共享契约

FastAPI OpenAPI 是 inbound 唯一契约源；上游查询用严格 Pydantic 模型导出独立 JSON Schema 与 fixture。两类快照都由 `contract:check` 防漂移。

健康响应让 API 与数据库状态分别可判：

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];
```

## 状态与边界

- 已具备：双库 API、鉴权、任务/SSE、会话查询、sync 调度与状态、上游 mock 契约与 pull、亮色壳、fixtures、数据链、E2E/门禁。
- 未具备：问题查询、自进化执行、真实 run 授权、用户停用界面。
- 明确不做：多租户、生产密钥读取、无评测证据的自动改代码。
