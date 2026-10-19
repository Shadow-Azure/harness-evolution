# Harness Evolution

面向 coding agent（先支持 Codex）的**轨迹查看与问题诊断服务**。

目标不是简单地“让模型改自己”，而是先建立可观察、可诊断、可验证的闭环：

1. 导入 agent 的真实执行轨迹。
2. 看清每一轮的目标、工具调用、错误与结果。
3. 识别轨迹中的问题，并回链到具体证据。
4. 把问题转化为 skill / prompt / 工具 / 控制流的最小改进项。
5. 用评测验证改动，再决定采纳或回滚。

> 当前状态：**M0 脚手架**。只初始化了前后端结构与健康检查，尚未实现轨迹解析、
> SQLite 存储和 AI 诊断。

## 当前结构

```text
apps/
  web/                 React + Vite 前端
  server/              Fastify + TypeScript 后端
packages/
  contracts/           前后端共享协议
docs/
  architecture.md      服务边界、数据流与数据层策略
  roadmap.md           M0–M3 路线图
  charter.md           实验与自进化协议
  metrics.md           指标定义
research/
  harness/             被测 harness 适配层
  tasks/               评测任务与评分器
  experiments/         对照实验记录
```

产品代码与研究资料分开。`research/` 保留原有的实验脚手架，后续自进化闭环会复用其中的
任务与指标定义。

## 快速开始

```bash
pnpm install
pnpm dev
```

- Web: http://localhost:5173
- API: http://127.0.0.1:4310/api/health

其他命令：

```bash
pnpm typecheck
pnpm build
pnpm start        # 只启动 API
```

## 当前 API

```text
GET /api/health
```

## 明确的阶段性边界

本阶段不包含：

- SQLite 数据库与迁移
- Codex session 解析
- LLM 调用与诊断
- 用户、权限与多租户
- Claude Code 或其他 agent 适配

下一步从 **M1：导入并查看一个真实 Codex session** 开始，具体见
[docs/roadmap.md](docs/roadmap.md)。架构取舍见
[docs/architecture.md](docs/architecture.md)。
