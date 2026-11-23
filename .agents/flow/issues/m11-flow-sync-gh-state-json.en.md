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

Read state and issue milestone membership. Reconcile metadata and bodies within the selected scope.

## Design authority

- [10 §2 Roadmap and task entry](../../../plans/fullstack-design/10-roadmap-draft.md): planning and task-management boundaries.

## Implementation

The milestone adapter reads state. The issue adapter reads state and a nullable milestone number, then PATCHes both fields when either differs. Bodies are compared and updated separately.

## Implementation steps

Exercise reads, writes and invalid responses at the CLI boundary. Test numbered selections and mutually exclusive flags.

## Dependencies and boundary

Depends on m7-01. Covers metadata for existing objects and scoped issue synchronization.

## Verification

```sh
pnpm test:gates
pnpm verify:flow
pnpm flow:sync
```

- Objects whose metadata already matches receive no PATCH, and issue creation/backfill and body synchronization finish.

## Acceptance

Matching metadata skips the state and milestone write. A milestone mismatch triggers an update even if state matches. Invalid JSON, missing fields and invalid issue selections produce errors.

## Gates and CI

- Gate, Flow, and live-sync verification.

## Non-goals

- Do not elevate or bypass GitHub permissions or suppress genuine state-update failures.
- Do not change the local Flow state machine or `--retire-missing` semantics.
