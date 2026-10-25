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
apps/api/app/
  main.py               FastAPI composition root
  api/                  domain routers
  service/              business rules and orchestration
  db/                   database and CRUD boundary
  third_party_api/      outbound API adapters
  middleware/           request context and identity boundary
```

依赖方向为 `api → service → db/third_party_api`。

## 当前请求链路

```text
Web ──► FastAPI middleware ──► api/health
                     │
                     └──► non-public /api/* → 401 AUTH_REQUIRED
```

`/api/health` 无需登录并返回 `ok/service/phase/version/db`；数据库故障返回 503，进程仍可达。其他 `/api/*` 默认 401；未知路由、校验失败与未捕获异常共用错误 envelope。

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

FastAPI OpenAPI 是唯一契约源。导出脚本生成 `packages/contracts/openapi.json` 快照，`openapi-typescript` 再从快照生成 `packages/contracts/src/generated/api.d.ts`；`src/index.ts` 只暴露稳定别名与跨端常量。`contract:check` 在临时目录重新生成并逐字比对，生成物手改或后端漂移都会在构建前失败。

健康检查响应是当前前后端的最小契约样本，数据库状态与 API 状态分别可判：

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];
```

类型围栏由 `verify-type-equiv` 与源码结构对账；生成类型漂移由 `contract:check` 拦截。

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

- 已具备：FastAPI 模块化骨架、统一错误模型、SQLite/MySQL Database 基座、Alembic 基线、健康检查、OpenAPI 契约生成与防漂移、Python lint/type/test 门禁。
- 未具备：领域表、真实鉴权、轨迹解析、问题查询、自进化执行。
- 明确不做：多租户、生产密钥读取、无评测证据的自动改代码。
