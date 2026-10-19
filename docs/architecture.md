# 架构草案

> 状态：M0 脚手架。本文用于先对齐边界，具体字段与接口会随第一个垂直切片迭代。

## 产品边界

当前阶段只做 Codex：

1. 导入本机 Codex session 轨迹。
2. 在前端按轮次浏览消息、推理、工具调用和输出。
3. 用规则或 AI 对轨迹做问题诊断。
4. 每条问题回链到具体轨迹，沉淀为可行动的改进项。

Claude Code、skill 自动改写、对照评测闭环属于后续阶段，不在首个切片内。

## 服务划分

```text
apps/
  web/                 React + Vite 前端
  server/              Fastify + TypeScript 后端
packages/
  contracts/           前后端共享协议
research/              原有的实验协议、任务与脚手架
docs/                  产品与架构文档
```

后端是模块化单体，不拆微服务。推荐按垂直切片组织：

```text
apps/server/src/
  app.ts                HTTP 组装入口
  sessions/             session 列表、详情、时间线
  ingest/               Codex rollout 扫描与解析
  storage/              repository 接口与 SQLite 实现
  analysis/             规则诊断、AI 诊断、分析任务
```

只有在出现独立扩缩容或隔离需求时才拆服务。

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

## 数据层策略

- 先使用 SQLite，数据库文件放在 `data/`，不提交入库。
- 业务代码只依赖 repository 接口，不直接拼接 SQL。
- 表结构保持通用，不使用 SQLite 专有数据类型；迁移脚本按版本管理。
- 轨迹原始记录与归一化视图分开存储，便于重新解析和排查。
- 切换到 Postgres 时替换 repository 实现与迁移脚本，不改 API 契约。

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

## 本阶段明确不做

- 不接数据库
- 不解析轨迹
- 不调用模型
- 不做用户体系与权限
- 不做多 agent 平台抽象

这些能力在骨架确认后按里程碑逐步加入。
