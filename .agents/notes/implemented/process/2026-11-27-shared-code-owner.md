# Agent Note: CODEOWNERS 增加共享 code owner

Status: implemented

[English](2026-11-27-shared-code-owner.en.md) | 中文

## Problem

`main` 的 ruleset `Protect main` 开启 `require_code_owner_review: true`，而 `.github/CODEOWNERS` 只登记 `@Shadow-Azure`。其他协作者的 approve 会计入必需审批数，却不满足 code owner 审查：PR 一直显示 “Approvals 1 still required”，只有仓库所有者再批准一次才能合入。HaleyBG 作为固定检视人，每次都被卡在最后一步；规则集 bypass 名单只能让她绕过规则合入，但那既改不了审查语义，也让合并界面继续显示被阻塞。

## Decision

把 `@HaleyBG` 与所有者并列登记进 CODEOWNERS 的 `*` 行，`require_code_owner_review` 保持不变：任一 code owner 的 approve 都满足 code owner 审查，HaleyBG 可以独立 approve + merge，所有者不再是最小审查瓶颈。

## Alternatives considered

- 移除 ruleset 的 `require_code_owner_review`：等价于任意一名协作者的 approve 都放行，失去“必须由指定 code owner 批准”的语义，且 CODEOWNERS 文件失效。
- 依赖 ruleset bypass（`User 68089448`、`pull_request`）：她能合入，但界面仍显示被阻塞，且这是无审查旁路，不符合“独立检视”。
- 给 HaleyBG admin 角色：权限过大，且不改变审查语义。

## Consequences

- 两名 code owner 中任一方的 approve 即可放行，审查职责由两人承担；PR 的必需审批数仍是 1，且必须来自其中的 code owner（作者不能自批）。
- HaleyBG 作为作者的 PR 仍需另一名 code owner 批准，这是 GitHub 平台限制，未在本决策内解决。
- `.github/CODEOWNERS` 的注释与 ruleset 的依赖关系必须同步维护，改名单时 update 注释。
