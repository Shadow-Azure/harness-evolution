# 架构

[English](architecture.en.md) | 中文

记录服务边界、数据流与存储；按垂直切片实现，理由见 `.agents/notes/`。

## 产品边界

含 fixture、本地导入、JSONL 归一化与 Agent 树组装；查询未运行。

## 服务划分

| 单元 | 技术 | 职责 |
|---|---|---|
| `apps/api` | Python 3.12 + FastAPI | HTTP API、服务编排、存储与外部数据边界 |
| `apps/web` | Vue 3 + Vite | 路由、公共数据层与渐进加载的业务页面 |
| `packages/contracts` | TypeScript | 前端共享协议与领域类型 |
| `research/` | Markdown + YAML | 评测任务、harness 适配、实验记录 |

路由只在 `apps/api/app/main.py` 注册；依赖方向为 `api → service → db/third_party_api`。

## 垂直切片

```text
main.py
api/
service/
db/
third_party_api/
middleware/
```

## 当前请求链路

```text
Web ──► middleware ──► public endpoints | bearer APIs | ticket-authenticated SSE → api routers
```

仅健康、登录、刷新和票据 SSE 公开；其余 API 需 Bearer JWT，`/api/users` 仅管理员。access 有效 30 分钟；refresh cookie 有效期 14 天，`httpOnly`、`SameSite=Strict`、路径 `/api/auth`。登录限流，强改密只放行必要端点，错误共用 envelope。

Web 先恢复会话再挂载路由；token 与用户只留内存。守卫处理登录和强改密；并发 401 单飞刷新并各重放一次；退出清 query cache。

## 数据层策略

- 生产数据库目标为 MySQL 8，本地快跑与自动化测试使用 SQLite；`HE_DB_DIALECT` 是唯一选择点。
- `Database` 接口统一管理连接生命周期、只读 session、写事务和 health；`api/service` 不直接创建 engine。
- Alembic 维护一棵双方言迁移树，SQLite 变更使用 batch 模式；业务代码只依赖 `db/crud/` repository 与 `Database` 接口，不直接拼接 SQL。
- `job_runs` 是真值；串行 worker 写 run 级 `evolution_run_events`，事件总线只广播有界通知，中断事件先落库。
- 原始 payload 按 `(root_session_id, agent_id)` 唯一保存；fixtures 通过 CLI 幂等写同构表。
- 归一化按 payload 独立解析，消息与内容块只在内存中存在；输出用户输入锚点、Agent/Skill/Workflow 触发点和统计。
- 本地导入写 payload/meta 与未处理索引；重跑保留运行态，其他状态不入库。
- 问题和归因由外部系统写入，服务只读。
- 密钥只从环境变量注入，不入仓库或数据库。

## API

```text
GET /api/health
POST /api/auth/{login,refresh,logout,change-password}
GET /api/auth/me
GET|POST /api/users
GET /api/jobs/{jobId}
POST /api/events/ticket
GET /api/events?ticket=…
```

票据绑定用户、topics 与游标，HMAC 认证，60 秒且单次消费；连接分页回放后实时，空闲 `ping`、尾游标 `reset`。run topic 资源经可注入 authorizer 校验；refresh 旋转拒绝重放，时间写 Asia/Shanghai。

## 共享契约

FastAPI OpenAPI 是唯一契约源。导出快照后由 `openapi-typescript` 生成类型，`src/index.ts` 只暴露稳定别名与常量；`contract:check` 临时重生成并逐字比对，构建前拦截漂移。

健康响应让 API 与数据库状态分别可判：

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];
```

## 状态与边界

- 已具备：双库 API、鉴权、任务/SSE、三入口壳、fixtures/seed、本地导入、Agent 树组装、E2E 与契约门禁。
- 未具备：会话查询/业务表树重写、问题查询、自进化执行、真实 run 授权、用户停用界面。
- 明确不做：多租户、生产密钥读取、无评测证据的自动改代码。
