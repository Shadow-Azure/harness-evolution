# AGENTS.md

Harness Evolution 是面向 coding agent 的轨迹查看与问题诊断服务。改代码先读 [docs/architecture.md](docs/architecture.md)；写文档先读 [docs/AGENTS.md](docs/AGENTS.md)；改流程先读 [.agents/flow/README.md](.agents/flow/README.md)。

## 文档与决策

- 文档分层遵循"一个事实一个 home"：现状进 `docs/`，决策理由进 `.agents/notes/`，开发流程进 `.agents/flow/`，事故叙事进 `docs/postmortem/`。
- 常驻文档中英成对（三件套）：改任一侧后最小修补另一侧，并运行 `pnpm record:i18n -- <pair>` 重录；契约见 [docs/i18n/README.md](docs/i18n/README.md)。
- 每个非平凡变更在同一 PR 内新增或更新至少一条 Agent Note；规则见 [.agents/notes/README.md](.agents/notes/README.md)。
- 写作以现状为准，不写变更史；段落一行到底，表格与代码块保持原样。

## 开发流程

- 流程树初始化后，代码改动必须先挂 `.agents/flow/` 的 issue；提交与 PR 标题含 `(#N)`，无豁免通道。
- 新 issue 用 `pnpm flow:new-issue -- …` 生成三件套；`pnpm flow:sync` 是流程树写 GitHub 的唯一入口。
- 优先级推进、状态机与 scope 约束见 [.agents/flow/README.md](.agents/flow/README.md)。
- PR 检视按 [docs/review.md](docs/review.md) 执行，检视文档落 `plans/`，不进入 Agent Notes。

## 命令

```sh
pnpm install             # 安装 workspace 依赖
pnpm dev                 # 同时启动 API 与 Web
pnpm build               # 构建 web
pnpm setup:api           # 创建 Python venv 并安装 API 依赖
pnpm lint:api            # FastAPI ruff 检查
pnpm typecheck:api       # FastAPI mypy 检查
pnpm test:api            # FastAPI pytest 与 coverage
pnpm typecheck           # 全 workspace 类型检查
pnpm test                # 各包测试
pnpm test:gates          # 门禁自测试
pnpm lint:docs           # 快速文档门禁（无构建）
pnpm verify:docs         # 全量文档门禁（含死链、ts 围栏编译、自测试）
pnpm verify:flow         # 流程树离线状态机
pnpm verify:flow-online  # 流程树与 GitHub 双侧一致（需 gh）
pnpm flow:sync           # 流程树 → GitHub（唯一写入口）
pnpm flow:new-issue -- … # 新建 issue 三件套
pnpm record:i18n -- <pair> # 双语配对重录
pnpm route:gates         # 按改动面推荐门禁
pnpm install:hooks       # 安装本地 git 钩子
```

## 代码惯例

- 后端保持模块化单体：HTTP 层只放 `api/` 路由，业务规则进 `service/`，存储隔离在 `db/` 接口与 repository 后，出站集成放 `third_party_api/`。
- `packages/contracts` 是前后端共享协议的唯一来源；跨端字段变化先改契约。
- 导出声明必须带 JSDoc；导出函数的每个形参写 `@param`，非 void 返回写 `@returns`。
- 常驻文档受词数预算约束，未登记预算即红门禁；超限处置顺序为搬层、压缩、提预算。
- 门禁脚本改动必须同步更新本文件命令清单与 `scripts/gates.spec.mjs`。

## 密钥

仓库不存密钥；`.env` 已 gitignore，服务不得读取生产凭据。
