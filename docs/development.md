# 开发指南

[English](development.en.md) | 中文

> 类型：教程 | 层级：贡献者上手。CI 与门禁的权威清单在 `package.json` scripts 与 [scripts/run-gates.mjs](../scripts/run-gates.mjs)，本页只讲怎么用。

## 环境

- Node ≥ 22、pnpm ≥ 10、Python ≥ 3.12。
- 首次 clone 后运行 `pnpm install && pnpm setup:api`；本地钩子用 `pnpm install:hooks` 安装。
- 需要 `gh` 已登录才能使用 `flow:sync` 与 `verify:flow-online`。
- API 文档与 OpenAPI 默认关闭；`pnpm dev` 显式开启，生产保持默认或显式设置 `HE_DOCS_ENABLED=false`。
- `pnpm dev` 默认 SQLite；MySQL 设 `HE_DB_DIALECT=mysql`、`HE_DB_URL`，凭据仅走环境。

## 开发流程

流程树初始化后，改动先立 issue：`.agents/flow/` 里 roadmap → milestone → issue 三层工作文件，契约与优先级推进规则见 [.agents/flow/README.md](../.agents/flow/README.md)。新 issue 用 `pnpm flow:new-issue -- …` 生成三件套；提交与 PR 标题含 `(#N)`；`pnpm flow:sync` 把流程树同步到 GitHub 并回填编号。

## 日常循环

```sh
pnpm dev
pnpm typecheck
pnpm typecheck:web
pnpm test:web
pnpm test:api
pnpm test:db
pnpm test:db:mysql
pnpm test:integration
pnpm test:all
pnpm contract:generate
pnpm contract:check
```

提交前按改动面选择门禁：

| 改动 | 本地跑 |
|---|---|
| 仅文档 / Agent Note | `pnpm lint:docs` |
| 前端代码 | `pnpm lint:web && pnpm typecheck:web && pnpm test:web && pnpm test:integration && pnpm verify:web-style && pnpm build && pnpm verify:bundle` |
| 后端代码 | `pnpm lint:api && pnpm typecheck:api && pnpm test:api && pnpm test:db && pnpm test:integration` |
| 契约或跨包类型 | `pnpm contract:check && pnpm typecheck && pnpm test:all` |
| 流程树 | `pnpm verify:flow` |
| 涉及文档示例或死链 | `pnpm verify:docs` |

不确定时运行 `pnpm route:gates`。

## 文档与配对

常驻文档中英成对。改任一侧后，在同一 PR 内最小修补另一侧，再运行 `pnpm record:i18n -- <pair>` 重录；契约见 [i18n/README.md](i18n/README.md)。标记为 `ts` 的围栏会被真实编译，标记为 `ts type-equiv` 的围栏与源码逐字对账。

## PR 检视

检视按 [review.md](review.md) 执行；需要结构化产出时使用 `.agents/skills/pr-review/SKILL.md`，处理检视意见使用 `.agents/skills/pr-review-fix/SKILL.md`。检视文档落 `plans/`，不进入 Agent Notes。

## 提交与发布

- 每个非平凡变更同一 PR 内带一条 Agent Note（新增或更新 owning note）。
- 提交信息用中文，标题带 issue 引用；正文说明动机、取舍与验证命令。
- 发布前跑 `pnpm verify:docs`、`pnpm verify:flow` 与完整测试；当前尚未配置发布流水线。
