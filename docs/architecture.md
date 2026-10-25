# 架构

[English](architecture.en.md) | 中文

记录当前服务边界、数据流与存储策略；实现按垂直切片推进，取舍理由见 `.agents/notes/`。

## 产品边界

轨迹诊断服务当前为 M1 平台骨架；轨迹、问题与自进化尚未进入运行链路。

## 服务划分

| 单元 | 技术 | 职责 |
|---|---|---|
| `apps/api` | Python 3.12 + FastAPI | HTTP API、服务编排、存储与外部数据边界 |
| `apps/web` | Vue 3 + Vite | 路由、公共数据层与渐进加载的业务页面 |
| `packages/contracts` | TypeScript | 前端共享协议与领域类型 |
| `research/` | Markdown + YAML | 评测任务、harness 适配、实验记录 |

路由只在 `apps/api/app/main.py` 注册；HTTP 层负责校验与鉴权，业务进 `service/`，存储与外部集成分别隔离在 `db/` 与 `third_party_api/`。

## 垂直切片

```text
main.py
api/
service/
db/
third_party_api/
middleware/
```

依赖方向为 `api → service → db/third_party_api`。

## 当前请求链路

```text
Web ──► middleware ──► public endpoints | bearer APIs | ticket-authenticated SSE → api routers
```

仅健康、登录、刷新和票据认证 SSE 公开；其余 API 需 Bearer JWT，`/api/users` 仅管理员。access 有效 30 分钟；refresh cookie 有效 14 天，`httpOnly`、`SameSite=Strict` 且路径限定 `/api/auth`。登录限流，强制改密只放行必要端点，失败共用错误 envelope。

Web 启动先恢复会话再挂载路由；token 与用户只留内存。守卫处理登录和强改密，并发 401 单飞刷新并各重放一次，退出清 query cache。

## 数据层策略

- 生产数据库目标为 MySQL 8，本地快跑与自动化测试使用 SQLite；`HE_DB_DIALECT` 是唯一选择点。
- `Database` 接口统一管理连接生命周期、只读 session、写事务和 health；`api/service` 不直接创建 engine。
- Alembic 维护一棵双方言迁移树，SQLite 变更使用 batch 模式；业务代码只依赖 `db/crud/` repository 与 `Database` 接口，不直接拼接 SQL。
- `job_runs` 是真值；串行 worker 写 run 级 `evolution_run_events`，事件总线只广播有界通知，中断事件先落库。
- 原始轨迹 payload 可重放且幂等；问题和归因由外部系统写入，本服务只读。
- 密钥只从环境变量注入，不进入仓库或数据库。

## 当前 API

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

## 当前状态与非目标

- 已具备：模块化 API、统一错误、双方言存储、users/job_runs 迁移、鉴权、用户与任务 API、SSE 基座、契约和 Python 门禁。
- 未具备：轨迹与自进化业务表、真实 event replay adapter、用户停用界面、轨迹解析、问题查询、自进化执行。
- 明确不做：多租户、生产密钥读取、无评测证据的自动改代码。
