# Agent Note: 用 merge queue 而非只靠 strict 验证合并结果

Status: implemented

[English](2026-11-25-merge-queue-over-strict.en.md) | 中文

## Problem

2026-11-25 的 #589 / #562 事故表明：两个 PR 各自在各自 base 上全绿，先后合入后拼出的 main 从未被任何 CI 验证过。`Protect main` 的 `strict_required_status_checks_policy` 只强制"base 前进后更新分支并重跑"，检查对象仍是旧 base 上的 PR head，不验证合并结果；并行 agent PR 场景下每次 base 前进都要求所有在途 PR 手动 rebase + 全量重跑（单测 lane 约 14 分钟），且"更新后、合并前 base 再次前进"的窗口依然存在。

## Decision

启用 GitHub merge queue：`Protect main` ruleset 增加 `merge_queue` 规则（squash 合并，`max_entries_to_build`/`max_entries_to_merge`/`min_entries_to_merge` 均为 1，按单维护者吞吐设置），保留 `required_status_checks: ci-ok` 与 strict 作为绕过队列直接合并时的兜底。`ci.yml` 增加 `merge_group` 触发器，保证队列构建产生 `ci-ok`；`docs-flow`/`flow-online` 保持 PR-only 的 `if`，diff 门禁已在 PR 执行，`ci-ok` 把 skipped 视为通过。操作流程见 [docs/development.md](../../../../docs/development.md)「合并流程：merge queue」。

## Alternatives considered

- **只靠 strict**：拒绝作为唯一手段。它压缩时间窗但不改变检查对象，人工 rebase 摩擦高且仍有残余窗口。
- **自建合并机器人**：拒绝。需要维护第三方编排与凭据，merge queue 是平台原生能力且仓库为 public。
- **启用 auto-merge**：本变更不包含，待观察队列吞吐后另行评估。

## Consequences

- 每次入队多一次全量 CI（复用现有 lane，单测 lane 约 14 分钟），换来"合入的必然是被验证过的合并结果"；队列第二个 PR 在第一个合入后自动基于新 main 重建，无需手动 rebase。
- 队列构建失败即重排，语义冲突在合入前被拦；代价是冲突发现时间后移到队列阶段。
- 回滚方式：在 ruleset 关闭 `merge_queue` 规则即恢复普通合并；strict 与 `ci-ok` required check 不变。
