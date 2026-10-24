# 开发指南

[English](development.en.md) | 中文

> 类型：教程 | 层级：贡献者上手。CI 与门禁的权威清单在 `package.json` scripts 与 [scripts/run-gates.mjs](../scripts/run-gates.mjs)，本页只讲怎么用。

## 环境

- Node ≥ 22、pnpm ≥ 10、Python ≥ 3.12。
- 首次 clone 后运行 `pnpm install && pnpm setup:api`；本地钩子用 `pnpm install:hooks` 安装。
- 需要 `gh` 已登录才能使用 `flow:sync` 与 `verify:flow-online`。
- 生产设 `HE_DOCS_ENABLED=false` 关闭 API 文档与 OpenAPI。

## 开发流程

流程树初始化后，改动先立 issue：`.agents/flow/` 里 roadmap → milestone → issue 三层工作文件，契约与优先级推进规则见 [.agents/flow/README.md](../.agents/flow/README.md)。新 issue 用 `pnpm flow:new-issue -- …` 生成三件套；提交与 PR 标题含 `(#N)`；`pnpm flow:sync` 把流程树同步到 GitHub 并回填编号。本地 `pnpm verify:flow` 校验状态机，CI 在 PR 上加跑 diff 校验与 GitHub 一致性 lane。

## 日常循环

```sh
pnpm dev          # API + Web development
pnpm typecheck    # Workspace type checks
pnpm test         # Workspace tests
pnpm test:api     # FastAPI tests and coverage
```

提交前按改动面选门禁（不要默认全量跑，穷尽覆盖归 CI）：

| 改动 | 本地跑 |
|---|---|
| 仅文档 / Agent Note | `pnpm lint:docs` |
| 前端代码 | `pnpm typecheck && pnpm build` |
| 后端代码 | `pnpm lint:api && pnpm typecheck:api && pnpm test:api` |
| 契约或跨包类型 | `pnpm typecheck && pnpm test` |
| 流程树 | `pnpm verify:flow` |
| 涉及文档示例或死链 | `pnpm verify:docs` |

不确定时跑 `pnpm route:gates`，按改动路径获取建议命令。

## 文档与配对

常驻文档中英成对。改任一侧后，在同一 PR 内最小修补另一侧，再运行 `pnpm record:i18n -- <pair>` 重录；契约见 [i18n/README.md](i18n/README.md)。标记为 `ts` 的围栏会被真实编译，标记为 `ts type-equiv` 的围栏与源码逐字对账。

## PR 检视

检视按 [review.md](review.md) 执行；需要结构化产出时使用 `.agents/skills/pr-review/SKILL.md`，处理检视意见使用 `.agents/skills/pr-review-fix/SKILL.md`。检视文档落 `plans/`，不进入 Agent Notes。

## 提交与发布

- 每个非平凡变更同一 PR 内带一条 Agent Note（新增或更新 owning note）。
- 提交信息用中文，标题带 issue 引用；正文说明动机、取舍与验证命令。
- 发布前跑 `pnpm verify:docs`、`pnpm verify:flow` 与完整测试；当前尚未配置发布流水线。
