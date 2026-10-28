# 拆分 build-and-docs 流水线为并发 lane

[English](m6-ci-lane-split.en.md) | 中文

```yaml flow
kind: issue
id: m6-09
milestone: m6
depends: []
priority: P1
status: done
scope:
  - .github/workflows/ci.yml
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 156
  url: https://github.com/Shadow-Azure/harness-evolution/issues/156
```

## 背景

CI 的 `.github/workflows/ci.yml` 把静态检查、单测、数据库测试、集成、E2E、构建、bundle 门禁和文档门禁全部串在 `build-and-docs` 一个 job 里串行执行（19 步，timeout 20 分钟），CI 墙钟时间等于全部步骤之和。逐一核对脚本实现后确认：除 `verify:bundle` 硬依赖 `pnpm build` 产物外，其余步骤互不依赖——E2E 自带 `run-api.mjs start` + `vite` 子进程不依赖构建产物，API 类步骤只依赖 Python venv，其余只依赖 `pnpm install`。串行是历史演进（文档门禁后期内嵌）的结果，不是依赖约束。

## 目标

- `build-and-docs` 拆成按环境分组的并发 lane job，CI 墙钟时间显著缩短（预期关键路径缩短一半以上）。
- 每次运行仍执行全部门禁，不引入路径过滤，保持"代码与文档没有旁路"原则不变。
- 新增 `ci-ok` 聚合 job 作为分支保护唯一 required check，`mysql`/`flow-online` 被 `if` 跳过时不误报失败。

## 设计依据

- [plans/fullstack-design/09-review-guide.md](../../../plans/fullstack-design/09-review-guide.md) R5/R8：契约防漂移（`contract:check`）与双库 CI（SQLite/MySQL）是每次运行必须执行的门禁，拆分只能改执行拓扑、不能减门禁。
- [plans/fullstack-design/01-architecture.md](../../../plans/fullstack-design/01-architecture.md)「契约防漂移」行：CI 校验"重新生成 = 无 diff"，是 `api-static` lane 收纳 `contract:check` 的依据。
- 实现与上述章节冲突时，以链接章节为准；本 issue 只改执行拓扑，不改变任何门禁内容与阈值。

## 实现内容

- `ci.yml` 的 `build-and-docs` 拆为七个并发 lane：`web-static`（lint:web + typecheck:web + verify:web-style）、`api-static`（lint:api + typecheck:api + contract:check）、`unit-tests`（test:web + test:api，覆盖率 ≥80% 判定保持单 job 不拆）、`db-sqlite`（test:db + fixtures 冒烟 + verify:local-data）、`e2e`（test:integration + test:e2e）、`build-lane`（build → verify:bundle + typecheck）、`docs-flow`（verify:docs + test:gates + verify-flow --diff）。
- 新增 `ci-ok` 聚合 job：`needs` 全部 lane，`if: always()` 下仅当存在 `failure`/`cancelled` 才失败，`skipped` 放行（覆盖 `flow-online` 的 PR-only 条件与 push 事件）。
- `mysql`、`flow-online` 保持原样；`concurrency`、`permissions` 顶层配置不变。

## 实施步骤

1. 在 `ci.yml` 中按上述分组改写 jobs，每个 lane 自带 checkout + pnpm/pip setup（共享缓存）。
2. 追加 `ci-ok` 聚合 job，用 `needs.*.result` 数组表达式判失败/取消。
3. 本地跑 `actionlint` 等价校验（yaml 解析 + 表达式目检）与 `pnpm test:gates`、`pnpm verify:flow`。

## 依赖与交付边界

- 依赖：无。
- 交付边界：只改 `.github/workflows/ci.yml` 与流程文件、Agent Note；分支保护规则（把 required check 从 `build-and-docs` 迁到 `ci-ok`）是仓库设置操作，在 PR 合并前后台完成，不在本 issue diff 内。
- 非目标：不加路径过滤（path filter）；不拆覆盖率合并（`unit-tests` 保持单 job）；不做 E2E 按文件分片；不改任何门禁脚本内容。

## 独立验证

```sh
pnpm verify:flow && pnpm test:gates && pnpm lint:docs
```

- 三条命令退出码均为 0，无新增红门禁。

```sh
node -e "const yaml=require('./node_modules/.pnpm/node_modules/yaml/dist/index.js');const fs=require('fs');const d=yaml.parseDocument(fs.readFileSync('.github/workflows/ci.yml','utf8'));console.log(Object.keys(d.toJS().jobs).join(','))"
```

- 输出包含 `web-static,api-static,unit-tests,db-sqlite,e2e,build-lane,docs-flow,mysql,flow-online,ci-ok`，yaml 可解析。

## 验收标准

- `ci.yml` 中原 `build-and-docs` 的全部步骤都能在某个 lane 中找到，无门禁被丢弃或弱化。
- `ci-ok` 在任一 lane 失败时失败、在 `flow-online` 被跳过时（push 事件）仍通过。
- `pnpm verify:flow`、`pnpm test:gates` 全绿；提交与 PR 标题含 `(#N)`。

## 门禁与 CI

- `pnpm verify:flow` / `verify-flow --diff`：issue 资格与 scope 覆盖（diff 只落在 scope glob 内）。
- `pnpm test:gates`：门禁自测试保持绿（未改门禁脚本）。
- 本地无法执行 GitHub Actions 运行时，首跑验证依赖 PR 触发的真实 CI；`ci-ok` 语义正确性以 `needs.*.result` 表达式的 GitHub Actions 官方语义为准。

## 非目标

- 不引入路径过滤或 merge queue 调优。
- 不合并覆盖率产物、不做跨 job coverage 聚合。
- 不优化 E2E 串行策略（`--test-concurrency=1` 维持现状，另立 issue 评估分片）。
