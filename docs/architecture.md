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

仅健康、登录、刷新和票据 SSE 公开；其余 API 需 Bearer JWT，`/api/users` 与手动 sync 仅管理员。access 有效 30 分钟；refresh cookie 有效期 14 天，`httpOnly`、`SameSite=Strict`、路径 `/api/auth`。登录限流，强改密只放行必要端点，错误共用 envelope。

Web 先恢复会话再挂载路由；token 与用户只留内存。守卫处理登录和强改密；并发 401 单飞刷新并各重放一次；退出清 query cache。

应用 lifespan 在迁移和 JobRunner 恢复之后启动 sync scheduler。默认 60 秒检查 pending，`0` 关闭定时；scheduler 与 admin 手动触发共用 coordinator、进程内锁和 durable `sync_lock`。无 pending 不建 job，顶栏只显示真实状态。

## 数据层策略

- 生产数据库目标为 MySQL 8，本地快跑与自动化测试使用 SQLite；`HE_DB_DIALECT` 是唯一选择点。
- `Database` 接口统一管理连接生命周期、只读 session、写事务和 health；`api/service` 不直接创建 engine。
- Alembic 维护一棵双方言迁移树，SQLite 变更使用 batch 模式；业务代码只依赖 `db/crud/` repository 与 `Database` 接口，不直接拼接 SQL。
- `job_runs` 是真值；串行 worker 写 run 级 `evolution_run_events`，事件总线只广播有界通知，中断事件先落库。
- `sync_lock` 是跨触发单飞真值，默认 TTL 30 分钟；job 与锁在同一事务创建，terminal job 通过 runner hook 先终结异常 `sync_runs`，再释放匹配锁。重启重排保留旧 interrupted 审计并使用新的 replay run id。
- 原始 payload 按 `(root_session_id, agent_id)` 唯一保存；fixtures 通过 CLI 幂等写同构表。
- 归一化按 payload 独立解析，消息与内容块只在内存中存在；输出用户输入锚点、Agent/Skill/Workflow 触发点和统计。
- 重放按 root 原子执行：先解析/组装，再事务重写并推进 source 游标。
- 问题和归因由外部系统写入，服务只读。
- 密钥只从环境变量注入，不入仓库或数据库。

## 共享契约

FastAPI OpenAPI 是唯一契约源，覆盖 health、身份、用户、sessions、jobs、acquisition 与 events。快照由 `openapi-typescript` 生成类型，`contract:check` 逐字防漂移。

健康响应让 API 与数据库状态分别可判：

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];
```

## 状态与边界

- 已具备：双库 API、鉴权、任务/SSE、会话查询、sync 调度与状态、亮色壳、fixtures、数据链、E2E/门禁。
- 未具备：问题查询、自进化执行、真实 run 授权、用户停用界面。
- 明确不做：多租户、生产密钥读取、无评测证据的自动改代码。
