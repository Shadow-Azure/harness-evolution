# Agent Note: flow:sync parses state JSON

Status: implemented

English | [中文](2026-11-21-flow-sync-state-read.md)

## Problem

`pnpm flow:sync` re-PATCHed every numbered object when the remote and local trees had no drift: closing #445 on 2026-11-21 reported `状态更新 157`. The `gh()` helper in `scripts/flow-sync.mjs` returns a **string** from `execFileSync(...).trim()`, while `readMilestoneState` / `readIssueState` read `.state` from it as if it were a parsed object. `String.prototype.state` is always `undefined`, so the comparison with the desired state never matched and every object was treated as drifted. Body sync in the same command only increased when reconciliation really differed, which isolated the flaw to the state-read layer. `verify-flow-online` parses remote state with `JSON.parse` itself, so the online gate stayed green and hid the problem.

## Decision

- Read state after `JSON.parse`: add `githubStateReaders(repo, run)`, returning `readMilestoneState` / `readIssueState`; `run` returns gh's raw stdout and can be injected for gate self-tests. `main()` builds the readers with the real `gh` and injects them into `runSync`'s io.
- Add the internal `ghJson(args)` helper so milestone creation, the retire listing and state reads share one "parse first, then read fields" entry point and the same string-as-object mistake cannot return.
- A parsed state must be a non-empty string, otherwise the reader throws. Silently returning `undefined` would degrade sync into "always drifted, full PATCH on every run"; the failure should be loud instead of burning quota.
- `scripts/gates.spec.mjs` gains regressions: raw JSON from gh yields `open` / `OPEN`, a missing `state` throws, no drift yields `stateUpdates === 0`, and a single drift PATCHes only that object.

## Alternatives considered

- **Inline `JSON.parse` in the two readers only**: it fixes today, but the read logic would stay buried in the io literal inside `main()`, and gates could only exercise `runSync`'s injected stub, not the real wiring. Rejected; injectable readers make the wiring itself regressible.
- **Use `gh ... --jq .state` to get a bare string**: one less parse, but it couples gh's output format to the state comparison in the arguments, and the injection seam would have to mimic `--jq` output; the script would also end up with two state-read shapes. Rejected.
- **Reuse the JSON-aware `gh()` from `verify-flow-online.mjs`**: that helper belongs to the online gate; exporting it to the write entry point would make two scripts depend on each other and invert responsibilities. Rejected.

## Consequences

- Repeated `pnpm flow:sync` runs are idempotent again when there is no drift, and the `状态更新` count is trustworthy for real drift.
- The `runSync` contract and io shape are unchanged; body sync, creation and retire paths behave as before, and `ghJson` only replaces equivalent `JSON.parse(gh(...))` calls.
- If GitHub renames the state field or a read command returns non-JSON in the future, the reader throws instead of silently re-PATCHing; the reader and gate self-tests must change together then.
