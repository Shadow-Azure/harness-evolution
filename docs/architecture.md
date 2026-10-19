# 架构

[English](architecture.en.md) | 中文

记录当前服务边界、数据流与数据层策略。实现按垂直切片推进；本文写现状，取舍理由进 `.agents/notes/`。

## 产品边界

当前只做 Codex：

1. 导入本机 Codex session 轨迹。
2. 在前端按轮次浏览消息、推理、工具调用、输出与错误。
3. 用规则或 AI 对轨迹做问题诊断。
4. 每条问题回链到具体轨迹，沉淀为可行动的改进项。

Claude Code、skill 自动改写、对照评测闭环属于后续 milestone，不在 M1 切片内。

## 服务划分

| 单元 | 技术 | 职责 |
|---|---|---|
| `apps/web` | React + Vite | 轨迹浏览、诊断交互、问题看板 |
| `apps/server` | Fastify + TypeScript | HTTP API、入库、存储访问、分析编排 |
| `packages/contracts` | TypeScript | 前后端共享协议与领域类型 |
| `research/` | Markdown + YAML | 评测任务、harness 适配、实验记录 |

后端是模块化单体，不拆微服务；只有出现独立扩缩容或隔离需求时才拆服务。

## 垂直切片

```text
apps/server/src/
  app.ts                HTTP 组装入口
  sessions/             session 列表、详情、时间线
  ingest/               Codex rollout 扫描与解析
  storage/              repository 接口与 SQLite 实现
  analysis/             规则诊断、AI 诊断、分析任务
```

切片之间通过显式接口协作；路由只在 `app.ts` 注册，避免功能入口散落。

## 数据流

```text
~/.codex/sessions/**/*.jsonl
        │
        ▼
  ingest 解析与归一化
        │
        ▼
  SQLite（raw_records / sessions / turns / items）
        │
        ├──► REST API ──► Web 时间线
        │
        └──► analysis worker ──► findings ──► Web 问题看板
```

原始记录与归一化视图分开存储：解析规则升级时可以重放，不必重新读取用户目录。

## 数据层策略

- 先使用 SQLite，数据库文件放在 `data/`，不提交入库。
- 业务代码只依赖 repository 接口，不直接拼接 SQL。
- 表结构保持通用，不使用 SQLite 专有类型；迁移脚本按版本管理。
- 切换到 Postgres 时替换 repository 实现与迁移脚本，不改 API 契约。
- 导入必须幂等：同一 rollout 重复扫描不产生重复 session 或 turn。

## API 草案

```text
GET  /api/health
GET  /api/sessions
GET  /api/sessions/:id
GET  /api/sessions/:id/timeline
POST /api/ingest
POST /api/sessions/:id/analyze
GET  /api/analyses/:id
```

当前只实现 `GET /api/health`。后续接口先改 `packages/contracts` 再实现服务端，前端不自行复制字段定义。

## 共享契约

健康检查响应是前后端的第一份契约样本：

```ts type-equiv
/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export interface HealthResponse {
  ok: boolean;
  service: "harness-evolution";
  phase: ServicePhase;
}
```

类型围栏由 `verify-type-equiv` 与源码逐字对齐；契约漂移即红。

前端消费契约的最小示例（由 `doc-typecheck` 真实编译）：

```ts
import type { HealthResponse } from "./packages/contracts/src/index";

const health: HealthResponse = {
  ok: true,
  service: "harness-evolution",
  phase: "scaffold",
};
```

## 当前状态与非目标

- 已具备：workspace、前端壳、后端壳、共享契约、健康检查。
- 未具备：数据库、迁移、轨迹解析、诊断、模型调用、用户体系。
- 明确不做：多租户、权限、生产密钥访问、无评测证据的自动改代码。
