# 架构

[English](architecture.en.md) | 中文

记录当前服务边界、数据流与存储策略；实现按垂直切片推进，取舍理由见 `.agents/notes/`。

## 产品边界

轨迹诊断服务当前只交付 M1 平台骨架；轨迹、问题和自进化数据尚未进入运行链路。

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
Web ──► middleware ──► public endpoints | bearer APIs → api routers
```

只有健康、登录和刷新公开；业务 API 读取 bearer JWT，`/api/users` 仅管理员可用，OpenAPI 以 `BearerAuth` 声明受保护操作。登录按 IP 限制为每分钟 10 次，强制改密只放行改密、登出和当前身份。access 有效 30 分钟；refresh cookie 有效 14 天，`httpOnly`、`SameSite=Strict`、路径限定 `/api/auth`，生产加 `Secure`。健康检查在数据库故障时返回 503，各类失败共用错误 envelope。

## 数据层策略

- 生产数据库目标为 MySQL 8，本地快跑与自动化测试使用 SQLite；`HE_DB_DIALECT` 是唯一选择点。
- `Database` 接口统一管理连接生命周期、只读 session、写事务和 health；`api/service` 不直接创建 engine。
- Alembic 维护一棵双方言迁移树，SQLite 变更使用 batch 模式；业务代码只依赖 `db/crud/` repository 与 `Database` 接口，不直接拼接 SQL。
- 原始轨迹 payload 可重放且幂等；问题和归因由外部系统写入，本服务只读。
- 密钥只从环境变量注入，不进入仓库或数据库。

## 当前 API

```text
GET /api/health
POST /api/auth/{login,refresh,logout,change-password}
GET /api/auth/me
GET|POST /api/users
POST /api/events/ticket
```

SSE 传输属于后续 milestone；票据绑定签发用户、`run:{rid}` topics 和游标，60 秒单次使用并按需清理。refresh 旋转原子拒绝并发重放，撤销记录随令牌到期清理。空库用环境凭据播种必须改密的管理员；密码用 argon2id，公共用户响应不含密码或哈希，应用时间戳写 Asia/Shanghai。

## 共享契约

FastAPI OpenAPI 是唯一契约源。导出快照后由 `openapi-typescript` 生成类型，`src/index.ts` 只暴露稳定别名与常量；`contract:check` 临时重生成并逐字比对，构建前拦截漂移。

健康响应让 API 与数据库状态分别可判：

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];
```

## 当前状态与非目标

- 已具备：模块化 API 骨架、统一错误、双方言数据库基座、users 迁移、真实鉴权、用户 API、SSE 票据签发、健康检查、契约管线、Python 门禁。
- 未具备：业务领域表、SSE 传输、用户停用界面、轨迹解析、问题查询、自进化执行。
- 明确不做：多租户、生产密钥读取、无评测证据的自动改代码。
