# Agent Note: Use merge queue instead of relying on strict alone to verify the merge result

Status: implemented

English | [中文](2026-11-25-merge-queue-over-strict.md)

## Problem

The #589 / #562 incidents on 2026-11-25 showed that two PRs were each green on their own base, yet the combined main produced by merging them in sequence was never verified by any CI run. `strict_required_status_checks_policy` on `Protect main` only forces "update the branch and rerun after the base advances"; the checked object is still the PR head on a stale base, not the merge result. With parallel agent PRs, every base advance demands manual rebase plus a full rerun for all in-flight PRs (the unit lane alone takes about 14 minutes), and the window where the base advances again after the update but before the merge remains.

## Decision

Enable GitHub merge queue: add a `merge_queue` rule to the `Protect main` ruleset (squash merge, `max_entries_to_build`/`max_entries_to_merge`/`min_entries_to_merge` all set to 1 for single-maintainer throughput), keeping `required_status_checks: ci-ok` and strict as the fallback for bypassing the queue. `ci.yml` gains a `merge_group` trigger so queue builds produce `ci-ok`; `docs-flow`/`flow-online` keep their PR-only `if` since the diff gates already ran on the PR, and `ci-ok` treats skipped as passing. The operating flow is documented in [docs/development.en.md](../../../../docs/development.en.md) under "Merge flow: merge queue".

## Alternatives considered

- **Strict alone**: rejected as the sole mechanism. It shrinks the time window but does not change the checked object, adds manual rebase friction, and leaves a residual window.
- **Self-built merge bot**: rejected. It would require maintaining third-party orchestration and credentials; merge queue is a native platform capability and the repository is public.
- **Auto-merge**: not part of this change; to be evaluated after observing queue throughput.

## Consequences

- Every enqueue costs one full CI run (existing lanes, about 14 minutes for the unit lane) in exchange for "only verified merge results land"; the second PR in the queue is rebuilt automatically on the new main after the first merges, with no manual rebase.
- A failed queue build triggers a re-queue, and semantic conflicts are caught before merge; the trade-off is that conflicts surface later, at the queue stage.
- Rollback: disabling the `merge_queue` rule in the ruleset restores ordinary merging; strict and the `ci-ok` required check stay unchanged.
