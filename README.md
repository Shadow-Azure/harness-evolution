# Harness Evolution

[English](README.en.md) | 中文

面向 coding agent（先支持 Codex）的轨迹查看与问题诊断服务：导入真实执行轨迹，按轮次看清目标、工具调用、错误与结果，把问题回链到证据，再转化为可评测的 harness 改进项。

## 当前状态

M0 工程基线：pnpm workspace、React + Vite 前端、Fastify + TypeScript 后端、共享 contracts 包与健康检查已打通。轨迹解析、SQLite 存储与诊断能力按 roadmap 逐步接入，边界见 [docs/architecture.md](docs/architecture.md)。

## 快速开始

```sh
pnpm install
pnpm dev
```

- Web：http://localhost:5173
- API：http://127.0.0.1:4310/api/health

## 文档与门禁

- 文档地图：[docs/README.md](docs/README.md)
- 文档标准：[docs/AGENTS.md](docs/AGENTS.md)
- 双语配对契约：[docs/i18n/README.md](docs/i18n/README.md)
- 开发流程：[.agents/flow/README.md](.agents/flow/README.md)
- 决策记录：[.agents/notes/README.md](.agents/notes/README.md)
- PR 检视：[docs/review.md](docs/review.md)

```sh
pnpm lint:docs     # 快速文档门禁
pnpm verify:docs   # 全量文档门禁
pnpm verify:flow   # 开发流程状态机
```

## 结构

```text
apps/web/          React + Vite 前端
apps/server/       Fastify + TypeScript 后端
packages/contracts 前后端共享协议
docs/              工程文档（分层见 docs/AGENTS.md）
.agents/flow/      roadmap / milestone / issue 流程树
.agents/notes/     设计决策记录
.agents/skills/    PR 检视、Computer Use 等可复用技能
research/          评测任务、harness 适配与实验记录
scripts/           零依赖门禁脚本
```
