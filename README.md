# Harness Evolution

[English](README.en.md) | 中文

面向 coding agent（先支持 Codex）的轨迹查看与问题诊断服务：导入真实执行轨迹，按轮次看清目标、工具调用、错误与结果，把问题回链到证据，再转化为可评测的 harness 改进项。

## 当前状态

M1 工程骨架推进中：pnpm workspace、React + Vite 前端、Python 3.12 + FastAPI 后端、共享 contracts 包与健康检查已打通。数据、鉴权、轨迹和诊断能力按 [路线图](docs/roadmap.md) 逐步接入，边界见 [架构](docs/architecture.md)。

## 快速开始

```sh
pnpm install
pnpm setup:api
pnpm dev
```

- Web：http://localhost:5173
- API：http://127.0.0.1:8787/api/health

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
apps/web/          React + Vite frontend
apps/api/          Python 3.12 + FastAPI backend
packages/contracts Shared protocols
docs/              Engineering docs (layers in docs/AGENTS.md)
.agents/flow/      Roadmap / milestone / issue tree
.agents/notes/     Decision records
.agents/skills/    Reusable review and Computer Use skills
research/          Evaluation tasks, adapters and experiments
scripts/           Dependency-free gates
```
