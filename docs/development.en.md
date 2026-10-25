# Development Guide

English | [中文](development.md)

> Type: tutorial | Layer: contributor onboarding. The authoritative list of CI and gates lives in `package.json` scripts and [scripts/run-gates.mjs](../scripts/run-gates.mjs); this page explains how to use them.

## Environment

- Node ≥ 22, pnpm ≥ 10 and Python ≥ 3.12.
- Run `pnpm install && pnpm setup:api` after the first clone; install local hooks with `pnpm install:hooks`.
- `gh` must be logged in for `flow:sync` and `verify:flow-online`.
- API docs and OpenAPI are closed by default; `pnpm dev` enables them explicitly and production keeps the default or sets `HE_DOCS_ENABLED=false`.
- `pnpm dev` defaults to SQLite; MySQL sets `HE_DB_DIALECT=mysql` and `HE_DB_URL`, with credentials only from the environment.

## Development flow

Once the flow tree is initialized, every change starts with an issue: `.agents/flow/` holds the roadmap → milestone → issue working files, with the contract and priority rules in [.agents/flow/README.md](../.agents/flow/README.en.md). Create a trio with `pnpm flow:new-issue -- …`; commits and PR titles carry `(#N)`; `pnpm flow:sync` writes the flow tree to GitHub and backfills numbers.

## Daily loop

```sh
pnpm dev
pnpm typecheck
pnpm typecheck:web
pnpm test:web
pnpm test:api
pnpm test:db
pnpm test:db:mysql
pnpm test:integration
pnpm test:all
pnpm contract:generate
pnpm contract:check
```

Choose gates by change surface before committing:

| Change | Run locally |
|---|---|
| Docs / Agent Note only | `pnpm lint:docs` |
| Web code | `pnpm lint:web && pnpm typecheck:web && pnpm test:web && pnpm test:integration && pnpm verify:web-style && pnpm build && pnpm verify:bundle` |
| Backend code | `pnpm lint:api && pnpm typecheck:api && pnpm test:api && pnpm test:db && pnpm test:integration` |
| Contracts or cross-package types | `pnpm contract:check && pnpm typecheck && pnpm test:all` |
| Flow tree | `pnpm verify:flow` |
| Documentation examples or links | `pnpm verify:docs` |

When unsure, run `pnpm route:gates`.

## Docs and pairing

Resident docs are paired across Chinese and English. After changing either side, minimally patch the other side in the same PR and run `pnpm record:i18n -- <pair>`; the contract is in [i18n/README.en.md](i18n/README.en.md). Fences marked `ts` are compiled for real, while fences marked `ts type-equiv` are compared verbatim with source.

## PR review

Review follows [review.en.md](review.en.md); use `.agents/skills/pr-review/SKILL.md` for structured output and `.agents/skills/pr-review-fix/SKILL.md` to address review comments. Review documents live in `plans/` and never enter Agent Notes.

## Commits and release

- Every non-trivial change carries one Agent Note in the same PR (new or updated owning note).
- Commit messages are written in Chinese, with the issue reference in the title; the body explains motivation, trade-offs and verification commands.
- Before release, run `pnpm verify:docs`, `pnpm verify:flow` and the full test suite; no release pipeline is configured yet.
