# PR 合入被 code owner 审查阻塞：把 HaleyBG 登记为共享 code owner

[English](bugfix-codeowners-shared-owner.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-70
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - .github/CODEOWNERS
  - .agents/**
adr: []
github:
  number: 661
  url: https://github.com/Shadow-Azure/harness-evolution/issues/661
```

## 背景

- 现象：PR #657 上 HaleyBG 已提交 APPROVED，但合入框仍显示 `Approvals 1 still required`，merge 按钮保持禁用并提示 `Merging is blocked due to failing merge requirements`；只有仓库所有者再批准一次才能合入。
- 机制：`main` 的 ruleset `Protect main` 开启了 `require_code_owner_review: true`，而 [`.github/CODEOWNERS`](https://github.com/Shadow-Azure/harness-evolution/blob/main/.github/CODEOWNERS) 只登记了 `@Shadow-Azure` 一个 code owner。GitHub 只把 code owner 的 approve 计入 code owner 审查；HaleyBG 的 approve 会计入 `required_approving_review_count: 1`，却不满足 code owner 审查，于是 PR 永远停在“1 still required”。
- 影响：HaleyBG 只能 approve、合不了；每个 PR 都要回到所有者做最后一次批准，与“她可以独立检视合入”的目标冲突，也让所有者成为固定瓶颈。
- 规则集 bypass（`User 68089448`、`bypass_mode: pull_request`）只让她合入时跳过规则，不改变审查语义；这是绕过审查，不是让她的检视生效，且合并界面仍显示被阻塞。

## 目标

- 把 `@HaleyBG` 与所有者并列登记进 CODEOWNERS：任一 code owner 的 approve 即可满足 `require_code_owner_review`，她可以独立 approve + merge。
- 保持 `ci-ok` 必需检查、必需审批数（1）、force push / 分支删除保护不变。
- 不扩大其他协作者权限，不依赖 ruleset bypass 完成合并。

## 设计依据

- [AGENTS.md 开发流程](https://github.com/Shadow-Azure/harness-evolution/blob/main/AGENTS.md)：代码改动必须先挂 `.agents/flow/` 的 issue，提交与 PR 标题含 `(#N)`，无豁免通道。
- [.agents/flow/README.md 门禁与拦截点](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/flow/README.md)：`verify-flow --diff` 校验引用 issue 的资格与 diff scope 覆盖。
- [09 §5 Review checklist](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/09-review-guide.md#L167)：检视职责与合并前置条件应显式、可复核。
- [CODEOWNERS 文件注释](https://github.com/Shadow-Azure/harness-evolution/blob/main/.github/CODEOWNERS)：「规则集 "Protect main" 的 require_code_owner_review 依赖此文件」，修改审查人名单必须同步该文件。

## 实现内容

- 把 `.github/CODEOWNERS` 的 `*` 行改为 `* @Shadow-Azure @HaleyBG`，并把首行注释更新为「所有文件必须由仓库所有者或 @HaleyBG 批准」。
- 新增 Agent Note `.agents/notes/implemented/process/2026-11-27-shared-code-owner.md`（含英文侧与 i18n 记录），记录引入共享 code owner 的原因与被否方案。

## 实施步骤

1. 修改 `.github/CODEOWNERS` 的 `*` 行与注释。
2. 新增 Agent Note 三件套（中文、英文、i18n 记录）。
3. 本地运行 `pnpm verify:flow`、`pnpm lint:docs`，提交与 PR 标题带 `(#N)`。
4. 合并后在测试 PR 上以 HaleyBG 账号 approve，确认合入框不再要求所有者审查，且所有者单方 approve 仍能放行。

## 依赖与交付边界

- 依赖：仓库 admin 权限（登记 code owner）；`main` 的 ruleset `Protect main` 保持现状。
- 交付边界：只改 CODEOWNERS 与流程记录；不改 CI workflow、不改应用代码。
- 平台约束：HaleyBG 作为作者的 PR 不能被自己 approve，仍需另一名 code owner（或 bypass）——不在本 issue 解决范围。

## 独立验证

```sh
pnpm verify:flow
pnpm lint:docs
pnpm verify:docs
```

- 以上命令全部通过；`git diff` 只含 `.github/CODEOWNERS` 与 `.agents/notes/implemented/process/2026-11-27-shared-code-owner.*`。
- 合并后在任一 PR 上以 HaleyBG 账号 approve，`gh pr view <n> --json reviewDecision` 返回 `APPROVED`，合入按钮可用。

## 验收标准

- `.github/CODEOWNERS` 的 `*` 行同时列出 `@Shadow-Azure` 与 `@HaleyBG`。
- HaleyBG 单方 approve 即满足 code owner 审查（`reviewDecision = APPROVED`），不再出现 “Approvals 1 still required”。
- 所有者单方 approve 仍能放行；`ci-ok` 仍是必需检查，未放宽。
- 文档与流程门禁（`verify:flow`、`lint:docs`、`verify:docs`）通过。

## 门禁与 CI

- 本地：`pnpm verify:flow`、`pnpm lint:docs`、`pnpm verify:docs`。
- PR：标题与每个 commit 标题带 `(#N)`；`docs-flow` lane 的 `verify-flow --diff` 校验 scope 覆盖。
- 合并：仍受 `ci-ok` 必需检查、必需审批数（1）、code owner 审查约束。

## 非目标

- 不改规则集本身：不删除 `require_code_owner_review`、不改 bypass 名单、不调整必需审批数。
- 不调整其他协作者的仓库角色或 review 权限。
- 不解决 GitHub 平台“作者不能自批自己 PR”的限制。
