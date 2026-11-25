# 开发指南

[English](development.en.md) | 中文

> 类型：教程 | 层级：贡献者上手。门禁见 [scripts/run-gates.mjs](../scripts/run-gates.mjs)。

## 环境

- Node ≥ 22、pnpm ≥ 10、Python ≥ 3.12。
- 首次 clone 后跑 `pnpm install && pnpm setup:api`；Git hooks 用 `pnpm install:hooks`。
- GitHub 流程命令需要 `gh` 登录。
- `pnpm dev` 开启 API 文档；生产默认关闭或设 `HE_DOCS_ENABLED=false`。
- `pnpm dev` 默认 SQLite；MySQL 设 `HE_DB_DIALECT`/`HE_DB_URL`，凭据仅走环境。
- AI Agent 三个设置：`AI_AGENT_PROVIDER`（默认 `claude-code`，`fake` 供测试）、`HE_AI_AGENT_CLAUDE_BIN`（默认 `~/.local/bin/claude`）、`HE_PATCH_SOURCE_MODE`（默认 `placeholder`，可选 `minimal-config`/`agent-edit`）；详见 [ai-agent.md](ai-agent.md)。
- 本地 session/生成库 gitignored；CI 只用合成 fixtures。

## 开发流程

改动先立 issue：`.agents/flow/` 的 roadmap → milestone → issue 工作文件，契约见 [.agents/flow/README.md](../.agents/flow/README.md)。新 issue 用 `pnpm flow:new-issue -- …` 生成三件套；提交与 PR 标题含 `(#N)`；`pnpm flow:sync` 同步到 GitHub 并回填编号。删除兼容层前按 [compatibility.md](compatibility.md) 清单执行。

## 日常循环

```sh
pnpm dev
pnpm typecheck
pnpm typecheck:web
pnpm test:web
pnpm test:api
pnpm test:api:serial
pnpm test:db
pnpm test:db:mysql
pnpm test:integration
pnpm test:e2e
pnpm performance:report [--local]
pnpm fixtures:check
pnpm fixtures:seed
pnpm data:import:sessions
pnpm data:normalize:sessions
pnpm data:tree:sessions
pnpm data:replay:sessions
pnpm verify:local-sessions
pnpm verify:local-data
pnpm test:all
pnpm contract:generate
pnpm contract:check
```

提交前按改动面选择门禁：

| 改动 | 本地跑 |
|---|---|
| 仅文档 / Agent Note | `pnpm lint:docs` |
| 前端代码 | `pnpm lint:web && pnpm typecheck:web && pnpm test:web && pnpm test:integration && pnpm test:e2e && pnpm verify:web-style && pnpm build && pnpm verify:bundle` |
| 后端代码 | `pnpm lint:api && pnpm typecheck:api && pnpm test:api && pnpm test:db && pnpm test:integration` |
| 契约或跨包类型 | `pnpm contract:check && pnpm typecheck && pnpm test:all` |
| 流程树 | `pnpm verify:flow` |
| 涉及文档示例或死链 | `pnpm verify:docs` |

不确定时跑 `pnpm route:gates`。

## 上游联调

真实上游是显式 opt-in：`HE_UPSTREAM_LIVE=1` 且 `HE_UPSTREAM_BASE_URL`/`HE_UPSTREAM_TOKEN` 齐备时 live 用例才访问；缺一即跳过。运行：

```sh
HE_UPSTREAM_LIVE=1 HE_UPSTREAM_BASE_URL=... HE_UPSTREAM_TOKEN=... pnpm test:api -- tests/m12-01-real-trace-upstream -m live_upstream
```

日志与重放入口见 [deployment.md](deployment.md)。

## 外部表契约联调

真实 bad_case/probe 表是显式 opt-in：`HE_EXTERNAL_CONTRACT_LIVE=1` 且存在只读目标（`HE_EXTERNAL_DB_DIALECT`+`HE_EXTERNAL_DB_URL`，或退回 `HE_DB_*`）时才访问真实库。运行：

```sh
HE_EXTERNAL_CONTRACT_LIVE=1 HE_EXTERNAL_DB_DIALECT=mysql HE_EXTERNAL_DB_URL=... pnpm test:api -- tests/m12-02-external-contract-live -m live_external
```

漂移与权限日志见 [deployment.md](deployment.md)。

## 文档与配对

常驻文档中英成对。改任一侧后最小修补另一侧并 `pnpm record:i18n -- <pair>` 重录；契约见 [i18n/README.md](i18n/README.md)。标记为 `ts` 的围栏会被真实编译，`ts type-equiv` 围栏与源码逐字对账。

## 合并流程：merge queue

PR 全绿后入队；队列基于最新 main 构造合并结果并跑 `ci-ok`（`docs-flow`/`flow-online` 跳过视为通过），通过即 squash 合入，失败修复后重排。回滚：ruleset `Protect main` 关闭 `merge_queue` 即恢复普通合并；理由见 [Agent Note](../.agents/notes/implemented/process/2026-11-25-merge-queue-over-strict.md)。

## PR 检视

检视按 [review.md](review.md) 执行；用 `.agents/skills/pr-review/SKILL.md` 产出结构化检视，用 `.agents/skills/pr-review-fix/SKILL.md` 处理检视意见。检视文档落 `plans/`，不进入 Agent Notes。

## 提交与发布

- 每个非平凡变更同一 PR 内带一条 Agent Note。
- 提交信息用中文，标题带 issue 引用；正文说明动机与验证命令。
- 发布前跑 `pnpm verify:docs`、`pnpm verify:flow` 与完整测试；当前尚未配置发布流水线。
