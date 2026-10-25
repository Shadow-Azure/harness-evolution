# AGENTS.md

轨迹诊断服务。改代码读 [architecture](docs/architecture.md)，写文档读 [docs rules](docs/AGENTS.md)，改流程读 [flow rules](.agents/flow/README.md)。

## 文档与决策

- 一个事实一个 home：现状进 `docs/`，理由进 `.agents/notes/`，流程进 `.agents/flow/`，事故进 `docs/postmortem/`。
- 常驻文档中英成对：改一侧后修补另一侧并运行 `pnpm record:i18n -- <pair>`；见 [docs/i18n/README.md](docs/i18n/README.md)。
- 每个非平凡变更在同一 PR 内新增或更新至少一条 Agent Note；规则见 [.agents/notes/README.md](.agents/notes/README.md)。
- 写作以现状为准，不写变更史；段落一行到底，表格与代码块保持原样。

## 开发流程

- 代码改动必须先挂 `.agents/flow/` 的 issue；提交与 PR 标题含 `(#N)`，无豁免通道。
- 新 issue 用 `pnpm flow:new-issue -- …` 生成三件套；`pnpm flow:sync` 是流程树写 GitHub 的唯一入口。
- 优先级推进、状态机与 scope 约束见 [.agents/flow/README.md](.agents/flow/README.md)。
- PR 检视按 [docs/review.md](docs/review.md) 执行，检视文档落 `plans/`，不进入 Agent Notes。

## 命令

```sh
pnpm install             # 安装依赖
pnpm dev                 # 启动 API/Web
pnpm build               # 构建
pnpm setup:api           # 安装 API 依赖
pnpm lint:api            # ruff
pnpm lint:web            # eslint
pnpm typecheck:api       # mypy
pnpm test:api            # API 测试
pnpm test:db[:mysql]     # 数据库测试
pnpm test:all            # 全测试
pnpm contract:generate   # 生成契约
pnpm contract:check      # 校验契约
pnpm typecheck           # TS 类型
pnpm typecheck:web       # Vue TS 类型
pnpm test                # 单测
pnpm test:gates          # 门禁测试
pnpm lint:docs           # 快档文档
pnpm verify:docs         # 全量文档
pnpm verify:bundle       # 首屏 bundle 边界
pnpm verify:web-style    # 设计 token 颜色源
pnpm verify:flow         # 流程
pnpm verify:flow-online  # 流程在线
pnpm flow:sync           # 发布流程
pnpm flow:new-issue -- … # 新 issue
pnpm record:i18n -- <pair> # 重录双语
pnpm route:gates         # 推荐门禁
pnpm install:hooks       # Git hooks
```

## 代码惯例

- 后端保持模块化单体：HTTP 层只放 `api/` 路由，业务规则进 `service/`，存储隔离在 `db/` 接口与 repository 后，出站集成放 `third_party_api/`。
- `packages/contracts` 是前后端共享协议的唯一来源；跨端字段变化先改契约。
- FastAPI OpenAPI 是接口契约源；`packages/contracts/openapi.json` 与生成类型禁止手改，改接口后运行 `pnpm contract:generate`。
- 前后端行为变更同步交付单元测试与跨栈集成测试；CI 必须实际执行测试，单测覆盖率不得低于 80%。
- 导出声明必须带 JSDoc；导出函数的每个形参写 `@param`，非 void 返回写 `@returns`。
- 常驻文档受词数预算约束，未登记预算即红门禁；超限处置顺序为搬层、压缩、提预算。
- 门禁脚本改动必须同步更新本文件与 `scripts/gates.spec.mjs`。

## 密钥

仓库不存密钥；`.env` 已 gitignore，服务不得读取生产凭据。
