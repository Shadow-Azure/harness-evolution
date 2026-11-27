# PR merges blocked by code-owner review: register HaleyBG as a shared code owner

English | [中文](bugfix-codeowners-shared-owner.md)

```yaml flow
kind: issue
id: bugfix-70
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - .github/CODEOWNERS
  - .agents/notes/**
adr: []
github:
  number: 661
  url: https://github.com/Shadow-Azure/harness-evolution/issues/661
```

## Background

- Symptom: on PR #657, HaleyBG submitted APPROVED, yet the merge box still shows `Approvals 1 still required`, the merge button stays disabled, and the tooltip reads `Merging is blocked due to failing merge requirements`; the owner must approve once more before the PR can merge.
- Mechanism: the `Protect main` ruleset enables `require_code_owner_review: true`, while [`.github/CODEOWNERS`](https://github.com/Shadow-Azure/harness-evolution/blob/main/.github/CODEOWNERS) lists only `@Shadow-Azure` as a code owner. GitHub counts only code-owner approvals toward code-owner review; HaleyBG's approval counts toward `required_approving_review_count: 1` but not code-owner review, so the PR stays at "1 still required".
- Impact: HaleyBG can approve but cannot merge, and every PR returns to the owner for a final approval, which contradicts the goal of letting her review and merge independently and keeps the owner a fixed bottleneck.
- The ruleset bypass (`User 68089448`, `bypass_mode: pull_request`) only lets her merge by skipping the rules; it does not change review semantics, still shows the merge box blocked, and is a review bypass rather than her review taking effect.

## Goals

- Register `@HaleyBG` next to the owner in CODEOWNERS: an approval from either code owner satisfies `require_code_owner_review`, so she can approve and merge independently.
- Keep `ci-ok` as a required check, the required approval count (1), and force-push / branch-deletion protection unchanged.
- Do not widen other collaborators' permissions and do not depend on ruleset bypass to complete merges.

## Design authority

- [AGENTS.md development flow](https://github.com/Shadow-Azure/harness-evolution/blob/main/AGENTS.md): code changes must reference a `.agents/flow/` issue, and commit and PR titles must carry `(#N)`; there is no exemption channel.
- [.agents/flow/README.md gates and interception points](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/flow/README.md): `verify-flow --diff` validates the referenced issue and diff scope coverage.
- [09 §5 Review checklist](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/09-review-guide.md#L167): review ownership and merge preconditions should be explicit and auditable.
- [CODEOWNERS file comment](https://github.com/Shadow-Azure/harness-evolution/blob/main/.github/CODEOWNERS): "the `Protect main` ruleset's require_code_owner_review depends on this file", so the reviewer list change must update this file.

## Implementation

- Change the `*` line in `.github/CODEOWNERS` to `* @Shadow-Azure @HaleyBG` and update the first comment line to "all files must be approved by the repository owner or @HaleyBG".
- Add the Agent Note `.agents/notes/implemented/process/2026-11-27-shared-code-owner.md` (with its English side and i18n record), documenting why shared code ownership was introduced and which alternatives were rejected.

## Implementation steps

1. Update the `*` line and comment in `.github/CODEOWNERS`.
2. Add the Agent Note triplet (Chinese, English, i18n record).
3. Run `pnpm verify:flow` and `pnpm lint:docs` locally, and keep `(#N)` in the commit and PR titles.
4. After merge, approve a test PR as HaleyBG and confirm the merge box no longer requires the owner's review, while a single owner approval still merges.

## Dependencies and boundary

- Dependency: repository admin permission (registering a code owner); the `Protect main` ruleset stays as is.
- Boundary: only CODEOWNERS and the process record change; CI workflows and application code stay untouched.
- Platform constraint: a PR authored by HaleyBG cannot be self-approved and still needs another code owner (or bypass); out of scope here.

## Verification

```sh
pnpm verify:flow
pnpm lint:docs
pnpm verify:docs
```

- All commands pass; `git diff` contains only `.github/CODEOWNERS` and `.agents/notes/implemented/process/2026-11-27-shared-code-owner.*`.
- After merge, approve any PR as HaleyBG: `gh pr view <n> --json reviewDecision` returns `APPROVED` and the merge button is available.

## Acceptance

- The `*` line in `.github/CODEOWNERS` lists both `@Shadow-Azure` and `@HaleyBG`.
- A single HaleyBG approval satisfies code-owner review (`reviewDecision = APPROVED`); "Approvals 1 still required" no longer appears for her.
- A single owner approval still merges; `ci-ok` remains a required check and is not loosened.
- Documentation and flow gates (`verify:flow`, `lint:docs`, `verify:docs`) pass.

## Gates and CI

- Local: `pnpm verify:flow`, `pnpm lint:docs`, `pnpm verify:docs`.
- PR: commit and PR titles carry `(#N)`; the `docs-flow` lane's `verify-flow --diff` checks scope coverage.
- Merge: still gated by the `ci-ok` required check, required approval count (1), and code-owner review.

## Non-goals

- Do not change the ruleset itself: keep `require_code_owner_review`, keep the bypass list, and do not adjust the required approval count.
- Do not adjust other collaborators' repository roles or review permissions.
- Do not work around GitHub's platform rule that authors cannot approve their own PRs.
