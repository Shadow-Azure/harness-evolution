# Agent Note: A standing Bugfix milestone does not close when its issues are done

Status: implemented

English | [中文](2026-11-20-standing-bugfix-milestone.md)

## Problem

The Bugfix virtual milestone is designed to own every subsequent bugfix issue under one bucket instead of opening a milestone per problem. But `verify:flow` mechanically enforces "milestone done ⟺ all of its issues are done", and `flow:sync` maps a local `done` to a closed remote milestone. Once one bugfix completes and every flow-tree issue in that milestone is done, the close-out step also closes the remote standing bucket; meanwhile the remote milestone may already carry new bugfix issues (this time #434/#435 were not yet in the local flow tree), so closing it is both inaccurate and disruptive to later registration.

While closing #423, milestone #34 was briefly closed by `flow:sync`; the requester explicitly asked to keep the Bugfix milestone open, and it was reopened. The root cause is a missing "standing" concept in the flow model, not a one-off mistake.

## Decision

- The milestone yaml flow fence gains an optional `standing: true`; `bugfix-milestone` declares itself a standing bucket and keeps `active`.
- `verify:flow` skips the status ↔ "all issues done" equivalence for `standing: true` milestones: they may stay active when all issues are done, and may stay active while issues are still open; `flow:sync` maps `active` to open.
- Retiring a standing milestone requires an explicit roadmap decision: set `done` and then run `flow:sync`, instead of deriving it from issue completion.
- The rule lives in `.agents/flow/README.md` and its English side; `scripts/gates.spec.mjs` adds cases for a standing milestone passing and a non-boolean `standing` failing.
- The standing bucket sits at the end of the roadmap sequence, with new milestones inserted before it; its long-open acceptance issue must not block later milestones through cross-milestone same-priority serialization.
- Issue #423 was reopened by the proposer and stays ready until acceptance; the Bugfix milestone stays active/open and keeps owning subsequent bugfix issues.

## Alternatives considered

- **Keep automatic closing and reopen the milestone on every new bugfix**: this churns the remote state, and a new issue that is not yet in the local flow tree leaves local and remote inconsistent; it already happened here. Rejected.
- **Hard-code an exception for `id === "bugfix"` in the validator**: the rule would hide in implementation, cannot explain why only bugfix is special, and every future standing bucket needs another code change. An explicit `standing` field is readable, testable, and reusable. Rejected.
- **Read remote open issues inside the offline gate**: the offline gate must not depend on GitHub networking or live state, and CI token visibility differs; the standing semantics belong in local declarations. Rejected.

## Consequences

- A standing milestone's status is a human/roadmap decision and no longer derived from issue completion; forgetting to retire one will not turn the gate red, so roadmap review is the backstop.
- `standing` accepts booleans only; milestones without it keep the original equivalence, so existing milestones behave unchanged.
- `flow:sync` opens/closes remote milestones from status; #34 is reopened now, and the close-out PR keeps it open.
- The bugfix bucket sits after M27; future milestones must be inserted before the standing bucket, otherwise the same-priority block returns.
- The flow docs, gate self-tests, and this Note ship together; future standing buckets only need `standing: true`, without code changes.
