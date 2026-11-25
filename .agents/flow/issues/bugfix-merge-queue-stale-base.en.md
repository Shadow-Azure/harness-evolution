# Enable a merge queue so stale green checks cannot merge into a moved base

English | [中文](bugfix-merge-queue-stale-base.md)

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

## Background

### Scenario

The #589 / #562 incident on 2026-11-25 is the canonical sample:

- PR #589 was green at 02:03Z–02:16Z on head `6adde1d4`, when its base did not yet contain CaseTools.
- PR #562 merged `f9ad7434` at 03:09Z, adding `CaseTools` that calls the old writer CLI.
- PR #589 merged `744f4f57` at 06:21Z (changing the writer to the explicit-conclusion contract), and the merged result was never verified by any CI: each PR was green against its own base, and the combination was red.

One direct cause was that the `Protect main` ruleset had no required status checks; that gap was closed on 2026-11-25 (`required_status_checks: ci-ok`, `strict_required_status_checks_policy: true`). But `strict` only means "update the branch and re-run once the base moves"; it does not change what is verified — it never tests "does this PR still hold after another PR merges first". It only shortens the window by forcing a manual rebase and a full re-run.

### Analysis

- Cost of `strict`: the unit lane takes ~14 minutes; every time the base moves (common with parallel agent PRs) every in-flight PR must be updated and re-run, which is high manual friction, and there is still a window where the base moves again after the update and before the merge.
- Merge queue semantics: once a PR enters the queue, GitHub builds the merge result against the **latest main in the queue** and runs the required checks on that result; only then does it merge, and the next PR is rebuilt on the new main automatically. It verifies the merged result, not the PR head against an old base.
- Current state: the repository is public and supports merge queues; `.github/workflows/ci.yml` only triggers on `pull_request` and `push`, with no `merge_group`; the `Protect main` ruleset has required status checks but no `merge_queue` rule. Adding only the ruleset rule without a `merge_group` trigger would mean the queued required check never appears and the queue would stall.

## Goals

- Add a `merge_queue` rule to the `Protect main` ruleset (squash merge; `max_entries_to_build` / `max_entries_to_merge` / `min_entries_to_merge_wait_minutes` sized for a single maintainer's throughput).
- Add a `merge_group` trigger to `.github/workflows/ci.yml` so the `ci-ok` aggregate runs in queue builds.
- Keep `docs-flow` / `flow-online` PR-only (`if: github.event_name == 'pull_request'`; the diff gate already ran on the PR), and rely on `ci-ok` treating skipped lanes as passing.
- Keep `strict_required_status_checks_policy: true` as the fallback for direct merges that bypass the queue.
- Document the merge flow (PR → enqueue → queue build → merge) and the rollback path.

## Design authority

- [`.agents/flow/README.en.md`](../README.en.md): the GitHub-sync and gate contract; the `(#N)` PR/commit rule and diff-scope rule are unchanged.
- [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml): the `ci-ok` aggregate lane and its "skipped counts as passing" semantics.
- [docs/development.en.md](../../../docs/development.en.md): the contributor loop and gate summary, which need the merge-queue instructions.

## Implementation

- Ruleset: add `merge_queue` to `Protect main` (`merge_method: squash`; grouping and concurrency caps sized for CI duration; initial suggestion `max_entries_to_build: 1`, `max_entries_to_merge: 1`, `min_entries_to_merge: 1`), keeping the existing `required_status_checks` (`ci-ok`, strict).
- `ci.yml`:
  - add `merge_group` to `on`;
  - confirm `ci-ok` still appears for `merge_group` events (the aggregate lane must not depend on PR-only event fields);
  - keep `docs-flow` / `flow-online` guarded to PR-only so the queue does not repeat the diff and online-consistency checks.
- Docs: add a "Merge flow: merge queue" section to `docs/development.md` / `.en.md` covering enqueue, queue build, failure re-queue, and rollback (disabling the ruleset's `merge_queue` rule restores plain merges).
- Agent Note: record why merge queue was chosen over strict-only and its cost.

## Implementation steps

1. Validate locally/on a test branch that `ci-ok` aggregates correctly under `merge_group` and that skipped lanes do not fail it.
2. Add `merge_group` to `ci.yml`; run `pnpm test:gates` and workflow syntax validation.
3. Add the `merge_queue` rule to the repository ruleset (requires repository admin).
4. Verify with two test PRs: enqueue both; confirm the second rebuilds on the first's merged main and passes; confirm a deliberately semantic-conflicting sample is blocked.
5. Update docs and the Agent Note; after merging, observe for a week before deciding whether to keep `strict`.

## Dependencies and boundary

- Dependencies: the `Protect main` required status checks (added 2026-11-25).
- Boundary: only the `ci.yml` trigger, the ruleset configuration, docs, and an Agent Note; no application code, tests, or check-content changes; no approval or bypass changes.

## Verification

```sh
pnpm test:gates
pnpm verify:flow
gh api repos/Shadow-Azure/harness-evolution/rulesets/25782062 --jq '.rules[].type'
```

- Expected: the ruleset rule list contains `merge_queue` and `required_status_checks`; `ci.yml` produces `ci-ok` for `merge_group`; two test PRs enqueue in order and the second queue build runs against the first's merged main; a semantic-conflict sample is blocked by the queue build.

## Acceptance

- `merge_group` triggers CI and `ci-ok` becomes the required check for queue builds; `docs-flow`/`flow-online` skip in the queue while `ci-ok` still passes.
- The second queued PR rebuilds on the new main automatically and passes; manual rebases are no longer required.
- A semantic-conflict sample cannot pass the queue build or be merged directly.
- `docs/development.md` / `.en.md` and the Agent Note are updated and `verify:docs` passes; disabling the `merge_queue` rule rolls back to plain merges.

## Gates and CI

- Hit: `pnpm test:gates`, `pnpm verify:flow`, `pnpm verify:docs` (docs changes), and CI's own lint/syntax.
- No new dependencies; queue builds reuse the existing lanes, costing one full CI run per enqueue (unit lane ~14 minutes).

## Non-goals

- No application code, test fixture, or `verify-flow --diff` semantic changes; `strict` is kept as a direct-merge fallback.
- No auto-merge enablement (evaluated separately); no approval-count, code-owner, or bypass changes.
- No self-hosted merge bot or third-party CI orchestration.
