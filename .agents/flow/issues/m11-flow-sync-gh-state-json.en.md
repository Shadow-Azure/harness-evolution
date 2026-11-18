# Fix GitHub state JSON parsing in flow sync

English | [中文](m11-flow-sync-gh-state-json.md)

```yaml flow
kind: issue
id: m11-08
milestone: m11
depends:
  - m7-01
priority: P1
status: done
scope:
  - scripts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 322
  url: https://github.com/Shadow-Azure/harness-evolution/issues/322
```

## Background

The `flow:sync` command adapter reads `.state` directly from the JSON strings returned by `gh ... --json state` and the milestone API, which always produces `undefined`. Even when remote state already matches, synchronization PATCHes every historical milestone and issue. An account allowed to maintain issues but not milestones then receives a 404 on the first milestone PATCH, after new issues have been created but before body and existing-plan updates can finish.

## Goals

- Parse remote state correctly from GitHub CLI JSON output.
- Avoid PATCH requests when remote state already matches and allow issue-body synchronization to continue.
- Lock the string-JSON adapter boundary with gate tests.

## Design authority

- [10 §2 Roadmap and task entry](../../../plans/fullstack-design/10-roadmap-draft.md): planning and task-management boundaries.

## Implementation

- Export a pure GitHub-state JSON parser that fails fast on malformed JSON or a missing state.
- Reuse the parser from milestone and issue CLI adapters without changing the injected `runSync` interface.
- Add gate self-tests for lowercase milestone and uppercase issue states.

## Implementation steps

1. Add a failing test reproducing a JSON string read as an object.
2. Implement shared parsing and connect both read adapters.
3. Run gates, Flow verification, and one live `flow:sync` regression.

## Dependencies and boundary

- Depends on: m7-01.
- Boundary: fix state reads and no-op PATCHes only; do not change GitHub permissions, retirement policy, or issue-body rendering.

## Verification

```sh
pnpm test:gates
pnpm verify:flow
pnpm flow:sync
```

- Objects whose state already matches receive no PATCH, and issue creation/backfill and body synchronization finish.

## Acceptance

- Remote `{"state":"closed"}` and `{"state":"OPEN"}` payloads return their original values.
- Non-JSON, missing state, or non-string state produces a diagnosable error.
- With current permissions, sync no longer stops on a no-op PATCH to an already closed milestone.

## Gates and CI

- Gate, Flow, and live-sync verification.

## Non-goals

- Do not elevate or bypass GitHub permissions or suppress genuine state-update failures.
- Do not change the local Flow state machine or `--retire-missing` semantics.
