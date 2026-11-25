# Development Guide

English | [中文](development.md)

> Type: tutorial | Layer: contributor onboarding. Gates are listed in [scripts/run-gates.mjs](../scripts/run-gates.mjs).

## Environment

- Node ≥ 22, pnpm ≥ 10, Python ≥ 3.12.
- Run `pnpm install && pnpm setup:api` after cloning; install hooks with `pnpm install:hooks`.
- GitHub flow commands need a `gh` login.
- `pnpm dev` enables API docs; production defaults closed or sets `HE_DOCS_ENABLED=false`.
- `pnpm dev` defaults to SQLite; MySQL sets `HE_DB_DIALECT`/`HE_DB_URL` with environment-only credentials.
- Three settings drive the AI Agent layer: `AI_AGENT_PROVIDER` (default `claude-code`; `fake` for tests), `HE_AI_AGENT_CLAUDE_BIN` (default `~/.local/bin/claude`) and `HE_PATCH_SOURCE_MODE` (default `placeholder`; accepts `minimal-config`/`agent-edit`); see [ai-agent.en.md](ai-agent.en.md).
- Local sessions/data stay gitignored; CI uses synthetic fixtures.

## Development flow

Once the flow tree exists, every change starts with an issue: `.agents/flow/` holds the roadmap → milestone → issue working files, with the contract in [.agents/flow/README.md](../.agents/flow/README.en.md). Create a trio with `pnpm flow:new-issue -- …`; commits and PR titles carry `(#N)`; `pnpm flow:sync` writes to GitHub and backfills numbers. Before deleting a compatibility layer, follow the checklist in [compatibility.en.md](compatibility.en.md).

## Daily loop

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

Choose gates by change surface before committing:

| Change | Run locally |
|---|---|
| Docs / Agent Note only | `pnpm lint:docs` |
| Web code | `pnpm lint:web && pnpm typecheck:web && pnpm test:web && pnpm test:integration && pnpm test:e2e && pnpm verify:web-style && pnpm build && pnpm verify:bundle` |
| Backend code | `pnpm lint:api && pnpm typecheck:api && pnpm test:api && pnpm test:db && pnpm test:integration` |
| Contracts or cross-package types | `pnpm contract:check && pnpm typecheck && pnpm test:all` |
| Flow tree | `pnpm verify:flow` |
| Documentation examples or links | `pnpm verify:docs` |

When unsure, run `pnpm route:gates`.

## Upstream integration

The real upstream is explicitly opt-in: the live case in `tests/m12-01-real-trace-upstream` reaches it only with `HE_UPSTREAM_LIVE=1` and both credentials, and skips otherwise. Run:

```sh
HE_UPSTREAM_LIVE=1 HE_UPSTREAM_BASE_URL=... HE_UPSTREAM_TOKEN=... pnpm test:api -- tests/m12-01-real-trace-upstream -m live_upstream
```

Logs and replay entry points are documented in [deployment.en.md](deployment.en.md).

## Live external-table contract

Real bad_case/probe tables are explicitly opt-in: the live test reaches a real database only when `HE_EXTERNAL_CONTRACT_LIVE=1` and a read-only target (`HE_EXTERNAL_DB_DIALECT`+`HE_EXTERNAL_DB_URL`, or `HE_DB_*` as a fallback) are present. Run:

```sh
HE_EXTERNAL_CONTRACT_LIVE=1 HE_EXTERNAL_DB_DIALECT=mysql HE_EXTERNAL_DB_URL=... pnpm test:api -- tests/m12-02-external-contract-live -m live_external
```

Drift and permission logs are documented in [deployment.md](deployment.en.md).

## Docs and pairing

Resident docs are paired across Chinese and English. After changing either side, minimally patch the other and rerun `pnpm record:i18n -- <pair>`; the contract is in [i18n/README.en.md](i18n/README.en.md). Fences marked `ts` are compiled for real; `ts type-equiv` fences are compared verbatim with source.

## Merge flow: merge queue

Once a PR is green, enqueue it; the queue builds the merge result against the latest main and runs `ci-ok` on it (`docs-flow`/`flow-online` are skipped and count as passing), then squash-merges on success — on failure, fix and re-queue. Rollback: disabling `merge_queue` in the `Protect main` ruleset restores ordinary merging; see the [Agent Note](../.agents/notes/implemented/process/2026-11-25-merge-queue-over-strict.en.md).

## PR review

Review follows [review.en.md](review.en.md); use `.agents/skills/pr-review/SKILL.md` for structured output and `.agents/skills/pr-review-fix/SKILL.md` to address review comments. Review documents live in `plans/` and never enter Agent Notes.

## Commits and release

- Every non-trivial change carries one Agent Note in the same PR.
- Commit messages are written in Chinese, with the issue reference in the title; the body explains motivation and verification commands.
- Before release, run `pnpm verify:docs`, `pnpm verify:flow` and the full test suite; no release pipeline is configured yet.
