# V2 delivery roadmap and evidence gate

English | [中文](m7-01-v2-delivery-roadmap.md)

```yaml flow
kind: issue
id: m7-01
milestone: m7
depends: []
priority: P0
status: in-progress
scope:
  - .agents/flow/**
  - .agents/notes/**
  - docs/roadmap*.md
  - docs/roadmap.i18n.yaml
  - plans/fullstack-design/**
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/proposed/process/2026-11-15-v2-delivery-roadmap.md
github:
  number: 222
  url: https://github.com/Shadow-Azure/harness-evolution/issues/222
```

## Background

PR #209 merged the V2 target-state design, but the flow tree still stops at M6. Session ccbdb2f0 also proves that revision, parent relation, and completion evidence must be resolved before attribution.

## Goals

- Add M7-M12 roadmap, milestone, and implementation issues.
- Close delivered M6 work and move unfulfilled work to M12 with predecessor links.
- Capture revision, relation, and knowledge-trigger requirements as an M9 gate.

## Design authority

- [15 §7–§9](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：实施顺序、验收重点与真实会话证据门禁。
- [README D21–D23](../../../plans/fullstack-design/README.md)：V2 顶层决策。

## Implementation

- Extend the roadmap with six milestones, 31 V2 issues, and 12 M12 migration issues.
- Mark m6-23, m6-24, and m6-25 done; close M6 and move six unfinished items to M12.
- Add a bilingual decision note and update the public roadmap.

## Implementation steps

1. Update roadmap and milestones.
2. Generate complete bilingual issue triplets.
3. Adjust M6 and existing V2 issue state.
4. Run flow/docs gates and sync GitHub.

## Dependencies and boundary

- Dependencies: none
- Boundary: planning, flow, and decision documents only.

## Verification

```sh
pnpm verify:flow; pnpm lint:docs
```

- The M7-M11 sequence, dependencies, and scopes pass offline validation.
- Bilingual pairing hashes are current.

## Acceptance

- The full M7-M12 plan is traceable.
- Every open M6 item is either delivered or represented by an M12 migration record.

## Gates and CI

- Flow, documentation, and PR diff gates pass.

## Non-goals

- No V2 production implementation.
- No unrelated M6 closure.
