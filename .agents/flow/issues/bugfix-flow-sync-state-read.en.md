# flow:sync state readers are always undefined and re-PATCH every flow object

English | [中文](bugfix-flow-sync-state-read.md)

```yaml flow
kind: issue
id: bugfix-08
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - scripts/flow-sync.mjs
  - scripts/gates.spec.mjs
  - .agents/**
  - plans/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-21-flow-sync-state-read.md
github:
  number: 458
  url: https://github.com/Shadow-Azure/harness-evolution/issues/458
```

## Background

Closing issue #445 on 2026-11-21 ran `pnpm flow:sync` right after `pnpm verify:flow-online` had passed with no local/remote drift, yet the command reported `state updates: 157`: nearly every numbered issue and milestone received one state PATCH. Checking each object confirmed that no remote state was actually wrong (closed stayed closed, open stayed open), but every sync re-PATCHes all flow objects. That burns GitHub API quota and makes the "state updates" counter useless for spotting real drift.

Reproduction: run `pnpm flow:sync` twice in a row on a drift-free `main`; the second run still reports roughly as many state updates as there are flow objects. The same command's `body updates` only grows when the bodies really differ, so the defect is isolated to state reading and comparison.

## Goals

- `readIssueState` / `readMilestoneState` return the real remote state, and `runSync` PATCHes only objects that truly differ.
- Re-running `pnpm flow:sync` with no drift reports `state updates: 0`, restoring idempotence.
- Gate self-tests pin "parse the remote state correctly, update nothing without drift, update only drifted objects", preventing regressions.

## Design authority

- [`.agents/flow/README.md` §GitHub sync](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/flow/README.en.md): `pnpm flow:sync` is the only writer from the flow tree to GitHub and maps local status to remote state (done ↔ closed, everything else ↔ open), so repeated syncs must be idempotent.
- [`scripts/flow-sync.mjs`](https://github.com/Shadow-Azure/harness-evolution/blob/main/scripts/flow-sync.mjs): `runSync` is contracted to read the remote state and PATCH only on a mismatch.
- This is flow-tooling repair; `plans/fullstack-design` has no matching chapter, so the design authority is the flow rules and the script contract. The #445 closure operations (PR #453, #456) are the real trigger record.

## Analysis

**Root cause**: `gh(args)` in `scripts/flow-sync.mjs` returns `execFileSync(...).trim()`, a **string**, while both state readers treat it as an already-parsed object:

```js
readMilestoneState(milestone) {
  return gh(["api", `repos/${repo}/milestones/${milestone.data.github.number}`]).state;
},
readIssueState(issue) {
  return gh(["issue", "view", String(issue.data.github.number), "--repo", repo, "--json", "state"]).state;
},
```

`String.prototype.state` is always `undefined`, so `undefined === desired` is always false and `runSync` calls `updateIssueState` / `updateMilestoneState` for every numbered object. Creation (`createIssue`) uses `JSON.parse(gh(...))` and body reading (`readIssueBody`) uses `--jq .body`, so neither is affected; the defect only hits state comparison. `verify-flow-online` parses with `JSON.parse` itself, so the online gate stayed green and hid the problem.

**How it was located**:

1. During the #445 closure, compared the green `verify:flow-online` result with flow:sync's `state updates: 157`.
2. Reviewed `readIssueState` / `readMilestoneState` and the `gh` helper's return type.
3. Reproduced in `node`: `.state` on a string is `undefined`, while `JSON.parse` yields `"OPEN"` / `"CLOSED"`.
4. Ran sync twice on a drift-free tree; the second run still reported many updates, ruling out one-off historical drift.
5. Checked remote states: nothing was wrongly opened or closed, so the impact is redundant writes and a misleading counter, not a state incident.

## Implementation

- Parse JSON in the state readers: `JSON.parse(gh([...])).state`; or use `gh api ... --jq .state` to read the raw string directly.
- Add a `ghJson(args)` helper (or a `{ json: true }` option on `gh`) shared by creation and state reading, so the "string treated as object" mistake cannot recur.
- Make the readers injectable or add boundary tests in `scripts/gates.spec.mjs`: when `gh` returns a raw JSON string, the reader must return `OPEN` / `CLOSED`, not `undefined`; also assert `runSync` reports `stateUpdates === 0` without drift and counts only drifted objects otherwise.

## Implementation steps

1. Write the regression test first and confirm it fails against the current code (string input → reader returns `undefined`).
2. Fix the readers (`JSON.parse` or `--jq`); the test turns green.
3. Run `pnpm flow:sync` twice on a drift-free `main`; the second run must report `state updates: 0`.
4. Create one drift (change a local issue status or close one remote issue) and confirm only that object is PATCHed and counted once.
5. Run `pnpm test:gates`, `pnpm verify:flow`, and `pnpm verify:flow-online`.

## Dependencies and boundary

- Depends on an authenticated `gh`; no new service, database, or credential.
- Boundary: only `scripts/flow-sync.mjs` and its gate self-tests. No changes to the state machine, priority rules, creation or retire semantics, and no bulk rewrite of remote objects.

## Verification

```sh
pnpm test:gates
pnpm verify:flow
pnpm verify:flow-online
# two consecutive syncs without drift: the second must report state updates: 0
pnpm flow:sync
pnpm flow:sync
```

- Before the fix: the second sync reports roughly one state update per flow object (157 measured on 2026-11-21).
- After the fix: the second sync reports `state updates: 0`; creating a single drift updates only that object.

## Acceptance

- With no drift, `pnpm flow:sync` reports `state updates: 0` and repeated runs are idempotent.
- With drift, only mismatched objects are PATCHed and the count matches reality.
- Gate self-tests cover the "raw JSON string → correct state" boundary, and the test is red before the fix.
- `pnpm test:gates`, `pnpm verify:flow`, and `pnpm verify:flow-online` are green.

## Gates and CI

- Local: `pnpm test:gates`, `pnpm verify:flow`, `pnpm verify:flow-online`.
- CI: the `docs-flow` lane runs `test:gates` and `verify:docs`; changes under `scripts/` update `scripts/gates.spec.mjs` per the repository rules, and `AGENTS.md` if command behavior changes.
- Commit and PR titles carry `(#N)`; `verify-flow --diff` checks scope coverage.

## Non-goals

- No flow-toolchain refactor, no new sync subcommand or dry-run mode.
- No changes to the state machine, priority progression, or retiring logic.
- No cleanup or rewrite of historical remote issues / milestones.
- No fix for the observed 2026-11-21 E2E `m3-session-browser` 1500x837 bottom-gap flake (separate issue).
