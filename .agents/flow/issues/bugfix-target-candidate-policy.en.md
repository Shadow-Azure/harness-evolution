# Configure potential bad-case sources per target across overview, automatic attribution and evolution

English | [中文](bugfix-target-candidate-policy.md)

```yaml flow
kind: issue
id: bugfix-64
milestone: bugfix
depends: []
priority: P2
status: backlog
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/ui-prototype-v2/**
  - .agents/notes/**
  - docs/**
  - .agents/flow/issues/bugfix-target-candidate-policy*
adr:
  - ../../notes/proposed/feature/2026-11-26-target-candidate-sources.md
github:
  number: 625
  url: https://github.com/Shadow-Azure/harness-evolution/issues/625
```

## Background

A Skill can report a problem before Skill C executes. The current wizard compares the case anchor with the earliest target occurrence, and the binding worker can schedule excluded rows. Users need reproducible, target-owned candidate selection.

## Goals

Let C select reports from A while preserving the original reporter and self/discovery type. Each target version reaches its own attribution conclusion.

## Prototype comparison

| Existing creation form on main at 36160c8e | Proposed first step |
| --- | --- |
| ![Current form](https://raw.githubusercontent.com/Shadow-Azure/harness-evolution/5f9948f9738f2059038d871ec90f5cbfabd7dcd9/plans/ui-prototype-v2/evidence/candidate-rules/before-create.png) | ![Proposed form](https://raw.githubusercontent.com/Shadow-Azure/harness-evolution/5f9948f9738f2059038d871ec90f5cbfabd7dcd9/plans/ui-prototype-v2/evidence/candidate-rules/after-create.png) |

| A selects its own self reports | C executes after A reports |
| --- | --- |
| ![A preview](https://raw.githubusercontent.com/Shadow-Azure/harness-evolution/5f9948f9738f2059038d871ec90f5cbfabd7dcd9/plans/ui-prototype-v2/evidence/candidate-rules/rule-A.png) | ![C preview](https://raw.githubusercontent.com/Shadow-Azure/harness-evolution/5f9948f9738f2059038d871ec90f5cbfabd7dcd9/plans/ui-prototype-v2/evidence/candidate-rules/rule-C.png) |

[Download the interactive HTML](https://github.com/Shadow-Azure/harness-evolution/blob/5f9948f9738f2059038d871ec90f5cbfabd7dcd9/plans/ui-prototype-v2/harness-evolution.html?raw=true). Open it with `?u=admin&page=overview&tab=targets&demo=candidate-rules`.

## Design authority

See [Database design §7.5](../../../plans/fullstack-design/06-database-design.md#75-v2-口径空间--触发点--潜在--归因三态) and [API design §4.20](../../../plans/fullstack-design/05-api-design.md#420-自进化预览与启动v2).

## Implementation

1. Both create flows validate object details, then open candidate rules. Save the object, Skill binding and policy together on final confirmation. Back preserves both drafts. Cancel creates nothing and schedules no job. Existing objects save metadata directly. Their overview cards show the active policy and a separate rule editor. Members can inspect rules and managers can edit.
2. Offer default, default plus custom sources, and custom sources only. Match exact Skill/Agent type and name, including the target itself. Support historical suggestions and free text without registering a source target. Require at least one report type per rule and one valid source for a custom mode.
3. Evaluate any target invocation in the same root Session. Support strictly before, strictly after, or presence only. Directional rules require a real anchor and comparable coordinates. Explain unknown order and post-processing anchors. Preserve default self and post-processing semantics.
4. Show proposed, added and removed cases, with per-rule anchor and invocation evidence. Count each case once per target version. Preview automatic attribution candidates and keep historical reports visible separately.
5. Share the matcher across overview, automatic attribution, the wizard and runs. Consume included cases only. Snapshot the applied rule version, match reasons and coordinates for each run or batch. Read legacy targets using the default policy.

## Implementation steps

Define storage, compatibility, role checks, validation, preview and save APIs. Extend the shared matcher and batch snapshots. Wire both create flows, overview and wizard to the saved policy.

## Dependencies and boundary

Apply workspace scope and any applicable [label filter from #582](https://github.com/Shadow-Azure/harness-evolution/issues/582) first. Historical scan triggers, lookback and cache reuse conditions remain design decisions.

## Verification

Use the linked prototype and A/B/C traces below. Run the same fixtures through API and browser tests and assert the exact selected IDs delivered to the automatic worker.

## Acceptance

- [ ] Final confirmation creates the object atomically. Cancel or failure leaves no partial object or job. Editing existing metadata remains a single step.
- [ ] On `A1 → B1 → A2 → B2`, A selecting its own self reports and Session presence includes both A1 and A2. Requiring a later A includes only the A1 report, witnessed by A2.
- [ ] On `A1 → C1`, C accepts the A report with a later-C rule. On `C1 → A1 → C2`, C2 witnesses the match and overlapping rules produce one case.
- [ ] Separate source kinds with identical names. Respect report type, order evidence, Session and workspace. An unobserved typed source saves and previews zero cases.
- [ ] Under identical inputs preview, automatic batches and runs select the same IDs. Removed candidates retain accessible historical reports and snapshots.

## Gates and CI

Run `pnpm contract:check`, `pnpm test:api`, `pnpm typecheck:web`, `pnpm test`, relevant `pnpm test:e2e` scenarios and `pnpm verify:flow`.

## Non-goals

Report ingestion changes, attribution verdict changes, production replay and historical recomputation policy are outside candidate selection.
