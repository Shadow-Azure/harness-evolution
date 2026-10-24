# 架构

[English](architecture.en.md) | 中文

记录当前服务边界、数据流与数据层策略。实现按垂直切片推进；本文写现状，取舍理由进 `.agents/notes/`。

## 产品边界

Harness Evolution 面向 coding agent 轨迹，提供可回链的会话浏览、问题归因与自进化运行。当前 M1 只交付平台骨架；轨迹、问题和自进化数据尚未进入运行链路。

## 服务划分

| 单元 | 技术 | 职责 |
|---|---|---|
| `apps/api` | Python 3.12 + FastAPI | HTTP API、服务编排、存储与外部数据边界 |
| `apps/web` | React + Vite | 当前开发壳；M1 后续切换 Vue 3 |
| `packages/contracts` | TypeScript | 前端共享协议与领域类型 |
| `research/` | Markdown + YAML | 评测任务、harness 适配、实验记录 |

后端是模块化单体。路由只在 `apps/api/app/main.py` 注册；HTTP 层只做校验、鉴权与响应，业务规则进入 `service/`，存储和第三方系统分别隔离在 `db/` 与 `third_party_api/`。

## 垂直切片

```text
apps/api/app/
  main.py               FastAPI composition root
  api/                  domain routers
  service/              business rules and orchestration
  db/                   database and CRUD boundary
  third_party_api/      outbound API adapters
  middleware/           request context and identity boundary
```

切片之间通过显式接口协作；依赖方向保持 `api → service → db/third_party_api`。

## 当前请求链路

```text
Web ──► FastAPI middleware ──► api/health
                     │
                     └──► non-public /api/* → 401 AUTH_REQUIRED
```

`/api/health` 无需登录并返回 `ok/service/phase/version/db`。数据库健康检查失败时 HTTP 返回 503，但 API 进程保持可达。身份实现落地前，其他 `/api/*` 路径默认拒绝；未知路由、校验失败与未捕获异常都使用统一错误 envelope。

## 数据层策略

- 生产数据库目标为 MySQL 8，本地快跑与自动化测试使用 SQLite；`HE_DB_DIALECT` 是唯一选择点。
- `Database` 接口统一管理连接生命周期、只读 session、写事务和 health；`api/service` 不直接创建 engine。
- Alembic 维护一棵双方言迁移树；空 SQLite 与 MySQL 都可升级到 head，SQLite 的变更使用 batch 模式。
- 业务代码只依赖 repository/Database 接口，不直接拼接 SQL。
- 原始轨迹 payload 是事实源；归一化数据必须可重放且幂等。
- 问题与归因数据由外部系统写入，本服务只读。
- 密钥只从环境变量注入，不进入仓库或数据库。

## 当前 API

```text
GET /api/health
```

其他草案端点属于后续 milestone，不表示已经实现。

## 共享契约

健康检查响应是当前前后端的最小契约样本，数据库状态与 API 状态分别可判：

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export interface HealthResponse {
  ok: boolean;
  service: "harness-evolution";
  phase: ServicePhase;
  version: string;
  db: DatabaseHealth;
}
```

类型围栏由 `verify-type-equiv` 与源码逐字对账；契约漂移即红。

前端消费契约的最小示例（由 `doc-typecheck` 真实编译）：

```ts
import type { HealthResponse } from "./packages/contracts/src/index";

const health: HealthResponse = {
  ok: true,
  service: "harness-evolution",
  phase: "scaffold",
  version: "0.1.0",
  db: {
    dialect: "sqlite",
    ok: true,
    latencyMs: 0.2,
  },
};
```

## 当前状态与非目标

- 已具备：FastAPI 模块化骨架、统一错误模型、SQLite/MySQL Database 基座、Alembic 基线、健康检查、Python lint/type/test 门禁。
- 未具备：领域表、真实鉴权、轨迹解析、问题查询、自进化执行。
- 明确不做：多租户、生产密钥读取、无评测证据的自动改代码。
