# Agent Note: CI 拆分为并发 lane 与 ci-ok 聚合门

Status: implemented

[English](2026-10-28-ci-lane-split.en.md) | 中文

## Problem

`ci.yml` 把静态检查、单测、数据库测试、集成、E2E、构建、bundle 与文档门禁全部串在 `build-and-docs` 一个 job 里，CI 墙钟时间是全部步骤之和（timeout 20 分钟）。逐步核对脚本实现后确认：除 `verify:bundle` 硬依赖 `pnpm build` 产物外，其余步骤互不依赖——E2E 自起 `run-api.mjs` + `vite` 子进程不需要构建产物，API 步骤只要 Python venv，其余只要 `pnpm install`。串行是文档门禁后期内嵌的历史结果，不是依赖约束。

## Decision

- `build-and-docs` 按环境拆成七个并发 lane：`web-static`、`api-static`、`unit-tests`、`db-sqlite`、`e2e`、`build-lane`、`docs-flow`；`mysql` 与 `flow-online` 维持原样。每个 lane 自带 checkout 与 pnpm/pip setup，缓存共享。
- 唯一真实的产物依赖（build → verify:bundle）收进 `build-lane` 内部串行；覆盖率 ≥80% 的判定保持在 `unit-tests` 单 job 内，不做跨 job coverage 聚合。
- 新增 `ci-ok` 聚合 job：`needs` 全部 lane、`if: always()`，用 `needs.*.result` 表达式只对 `failure`/`cancelled` 一票否决，`skipped` 放行——覆盖 `flow-online` 的 PR-only 条件在 push 事件下的跳过。分支保护的 required check 迁到 `ci-ok` 单点，后续增删 lane 只改 `needs` 列表。
- 每次运行仍执行全部门禁，不引入路径过滤，"代码与文档没有旁路"原则不变。

## Alternatives considered

- 路径过滤（docs-only PR 跳过 e2e/build lane）：收益更大，但违反仓库明文的 no-bypass 原则，门禁可被改文档的 PR 绕开；否。
- 把 `unit-tests` 拆成 web/api 两个 job：多一层并行，但 80% 覆盖率阈值变成跨 job 聚合问题，需要 coverage artifact 合并设施；复杂度不值，否。
- 保留单 job 只调 timeout：不解决墙钟问题，否。
- E2E 按文件分片到多 job：`m3-session-browser` 单文件是单点大头，但分片改变 `--test-concurrency=1` 语义并需 artifact 合并，另立 issue 评估。

## Consequences

- CI 关键路径从"全部步骤之和"降为"最长 lane + 一次聚合"，每个 lane 多付约 1–2 分钟 setup，净收益预期过半。
- 分支保护需一次性把 required check 从 `build-and-docs` 换成 `ci-ok`（仓库设置操作，PR 合并前后台完成）；漏换窗口期内旧 check 名会永久 pending。
- `ci-ok` 的正确性依赖 GitHub Actions 的 `needs.*.result` 语义；本地只能做 YAML 解析与表达式目检，首次真实运行是最终验证。
- lane 失败排查从单份日志变成按 job 看日志；`case` 输出行 `lane results:` 打印各 lane 结果便于定位。
