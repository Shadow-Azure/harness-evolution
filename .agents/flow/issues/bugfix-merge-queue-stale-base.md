# 启用 merge queue，避免旧 base 上的绿色检查直接合入

[English](bugfix-merge-queue-stale-base.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-61
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - .agents/**
  - .github/workflows/ci.yml
  - docs/**
  - plans/**
adr: []
github:
  number: 609
  url: https://github.com/Shadow-Azure/harness-evolution/issues/609
```

## 背景

### 问题场景

2026-11-25 的 #589 / #562 事故是典型样本：

- PR #589 的 CI 于 02:03Z–02:16Z 在 head `6adde1d4` 上全绿，当时的 base 还没有 CaseTools。
- PR #562 于 03:09Z 合入 `f9ad7434`，新增 `CaseTools`，按旧 writer CLI 调用。
- PR #589 于 06:21Z 合入 `744f4f57`（改 writer 为显式结论契约），合并结果从未被任何 CI 验证过：两个 PR 各自在各自 base 上都是绿的，拼在一起才红。

当时的直接原因之一是 `Protect main` ruleset 没有 required status checks；该缺口已于 2026-11-25 补齐（`required_status_checks: ci-ok`，`strict_required_status_checks_policy: true`）。但 `strict` 只解决“base 前进后必须更新分支并重跑”，并不改变检查对象——它仍然不验证“另一个 PR 先合入后，本 PR 的合并结果是否还成立”，只是用“手动 rebase + 全量重跑”把时间窗压短。

### 分析

- `strict` 的成本：单测 lane 约 14 分钟；每次 base 前进（并行 agent PR 场景下很常见），所有在途 PR 都要重新 update + 重跑，人工摩擦高，且仍然存在“更新后、合并前 base 再次前进”的窗口。
- merge queue 的语义：PR 进入队列后，GitHub 基于**队列中最新的 main** 构造合并结果，并对该结果跑 required checks；通过才合入，后一个 PR 会自动基于前一个合入后的 main 重建。它验证的正是“合并结果”，而不是“旧 base 上的 PR head”。
- 现状：仓库是 public，支持 merge queue；`.github/workflows/ci.yml` 只有 `pull_request` 与 `push` 触发，没有 `merge_group`；`Protect main` ruleset 只有 required_status_checks，没有 `merge_queue` 规则。若只加 ruleset 规则不加 `merge_group` 触发器，队列里的 required check 永远不会产生，队列会卡死。

## 目标

- 在 `Protect main` ruleset 增加 `merge_queue` 规则（squash 合并；`max_entries_to_build` / `max_entries_to_merge` / `min_entries_to_merge_wait_minutes` 按单维护者吞吐设置）。
- `.github/workflows/ci.yml` 增加 `merge_group` 触发器，保证 `ci-ok` 聚合在队列构建中运行。
- `docs-flow` / `flow-online` 保持 `if: github.event_name == 'pull_request'`（diff 门禁已在 PR 上执行）；`ci-ok` 已把 skipped 视为通过，因此队列构建不会因这两条 lane 跳过而失败。
- 保留 `strict_required_status_checks_policy: true` 作为“绕过队列直接合并”时的兜底。
- 文档记录合并流程（PR → 入队 → 队列构建 → 合入）与回滚方式。

## 设计依据

- [`.agents/flow/README.md`](../README.md)：GitHub 同步与门禁契约；PR 标题/提交 `(#N)` 与 diff scope 规则不变。
- [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml)：`ci-ok` 聚合 lane 的定义与“skipped 视为通过”的语义。
- [docs/development.md](../../../docs/development.md)：贡献者的日常循环与门禁摘要，需要补 merge queue 操作说明。

## 实现内容

- ruleset：`Protect main` 增加 `merge_queue`（`merge_method: squash`，`grouping_strategy` 与并发上限按 CI 时长设置；初始建议 `max_entries_to_build: 1`、`max_entries_to_merge: 1`、`min_entries_to_merge: 1`），保留现有 `required_status_checks`（`ci-ok`，strict）。
- `ci.yml`：
  - `on` 增加 `merge_group`；
  - 确认 `ci-ok` 在 `merge_group` 事件下正常产生（聚合 lane 不依赖 PR-only 事件字段）；
  - `docs-flow` / `flow-online` 的 `if` 条件保持 PR-only，避免队列中重复跑 diff 门禁与在线一致性检查。
- 文档：`docs/development.md` / `.en.md` 增加一节「合并流程：merge queue」，说明入队、队列构建、失败重排、回滚（关闭 ruleset 的 merge_queue 规则即恢复普通合并）。
- Agent Note：记录选择 merge queue 而非“只靠 strict”的理由与成本。

## 实施步骤

1. 本地/测试分支验证 `merge_group` 触发下 `ci-ok` 正常聚合且 skipped lane 不判红。
2. 改 `ci.yml` 增加 `merge_group`，跑 `pnpm test:gates` 与 workflow 语法校验。
3. 在仓库 setings/ruleset 增加 `merge_queue` 规则（需仓库管理员权限）。
4. 用两个测试 PR 验证：同时入队，第二个在第一个合入后自动重建并通过；构造一个语义冲突验证被拦。
5. 更新 docs 与 Agent Note，PR 合入后观察一周再决定是否保留 strict。

## 依赖与交付边界

- 依赖：`Protect main` 的 required_status_checks（已于 2026-11-25 补齐）。
- 交付边界：只改 `ci.yml` 触发器、ruleset 配置、docs 与 Agent Note；不改任何应用代码、测试或验证 lane 的检查内容；不改审批规则与 bypass 策略。

## 独立验证

```sh
pnpm test:gates
pnpm verify:flow
gh api repos/Shadow-Azure/harness-evolution/rulesets/25782062 --jq '.rules[].type'
```

- 预期：ruleset 规则列表出现 `merge_queue` 与 `required_status_checks`；`ci.yml` 在 `merge_group` 事件下产生 `ci-ok`；两个测试 PR 依次入队，第二个的队列构建基于第一个合入后的 main；语义冲突样本在队列构建中被拦。

## 验收标准

- `merge_group` 事件触发 CI，`ci-ok` 成为队列构建的 required check；`docs-flow`/`flow-online` 在队列中跳过但 `ci-ok` 仍通过。
- 队列中的第二个 PR 在第一个合入后自动基于新 main 重建并通过；不再需要手动 rebase。
- 语义冲突样本无法通过队列构建，也无法直接合并。
- `docs/development.md` / `.en.md` 与 Agent Note 更新，`verify:docs` 通过；关闭 merge_queue 规则可回滚为普通合并。

## 门禁与 CI

- 命中：`pnpm test:gates`、`pnpm verify:flow`、`pnpm verify:docs`（文档改动）、CI 自身的 lint/syntax。
- 不新增依赖；merge queue 构建复用现有 lane，成本为每次入队一次全量 CI（单测 lane 约 14 分钟）。

## 非目标

- 不改应用代码、测试夹具或 `verify-flow --diff` 语义；不移除 `strict`（保留为直接合并兜底）。
- 不启用 auto-merge（可另行评估）；不改审批人数、code owner 或 bypass 策略。
- 不引入自建合并机器人或第三方 CI 编排。
