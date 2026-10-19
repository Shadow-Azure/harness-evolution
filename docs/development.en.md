# Development Guide

English | [中文](development.md)

> Type: tutorial | Layer: contributor onboarding. The authoritative list of CI and gates lives in `package.json` scripts and [scripts/run-gates.mjs](../scripts/run-gates.mjs); this page explains how to use them.

## Environment

- Node ≥ 22 and pnpm ≥ 10.
- Run `pnpm install` after the first clone; install local hooks with `pnpm install:hooks`.
- `gh` must be logged in for `flow:sync` and `verify:flow-online`.

## Development flow

Once the flow tree is initialized, every change starts with an issue: `.agents/flow/` holds the roadmap → milestone → issue working files, with the contract and priority rules in [.agents/flow/README.md](../.agents/flow/README.en.md). Create a trio with `pnpm flow:new-issue -- …`; commits and PR titles carry `(#N)`; `pnpm flow:sync` writes the flow tree to GitHub and backfills numbers. `pnpm verify:flow` checks the state machine locally, while CI adds diff checks and the GitHub consistency lane on PRs.

## Daily loop

```sh
pnpm dev          # API + Web 并行开发
pnpm typecheck    # 跨包类型检查
pnpm test         # 各包测试
```

Choose gates by change surface before committing (do not default to everything; exhaustive coverage belongs to CI):

| Change | Run locally |
|---|---|
| Docs / Agent Note only | `pnpm lint:docs` |
| Web or server code | `pnpm typecheck && pnpm build` |
| Contracts or cross-package types | `pnpm typecheck && pnpm test` |
| Flow tree | `pnpm verify:flow` |
| Documentation examples or links | `pnpm verify:docs` |

When unsure, run `pnpm route:gates` to get suggested commands from changed paths.

## Docs and pairing

Resident docs are paired across Chinese and English. After changing either side, minimally patch the other side in the same PR and run `pnpm record:i18n -- <pair>`; the contract is in [i18n/README.en.md](i18n/README.en.md). Fences marked `ts` are compiled for real, while fences marked `ts type-equiv` are compared verbatim with source.

## PR review

Review follows [review.en.md](review.en.md); use `.agents/skills/pr-review/SKILL.md` for structured output and `.agents/skills/pr-review-fix/SKILL.md` to address review comments. Review documents live in `plans/` and never enter Agent Notes.

## Commits and release

- Every non-trivial change carries one Agent Note in the same PR (new or updated owning note).
- Commit messages are written in Chinese, with the issue reference in the title; the body explains motivation, trade-offs and verification commands.
- Before release, run `pnpm verify:docs`, `pnpm verify:flow` and the full test suite; no release pipeline is configured yet.
