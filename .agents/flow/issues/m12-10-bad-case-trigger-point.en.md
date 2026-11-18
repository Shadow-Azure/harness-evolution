# Expose locatable bad-case trigger points

English | [中文](m12-10-bad-case-trigger-point.md)

```yaml flow
kind: issue
id: m12-10
milestone: m12
depends:
  - m8-04
  - m12-02
  - m12-07
priority: P1
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 337
  url: https://github.com/Shadow-Azure/harness-evolution/issues/337
```

## Background

Production replaces the prototype's "trigger point" column with "trigger time", populated from `BadCaseListItem.triggerAt`. The API design explicitly says `triggerAt` mirrors `createdAt` until m9-04 settles trigger coordinates, so callers must not treat it as the true trigger time or a sort key.

The prototype shows `L0`, `L58`, `L91`, and similar log lines, allowing users to map a bad case directly to the highlighted line in the execution flow. Production instead shows a timestamp, losing locatability and implying a real trigger time that is not yet available.

`bad_cases` may already carry `trigger_line`; the overview contract and read model do not project it into `BadCaseListItem`, forcing the frontend to use the temporary `triggerAt` value.

## Goals

- Expose nullable `triggerLine` on overview bad-case rows while preserving `triggerAt` for compatibility.
- Rename the frontend column to "trigger point", render `L<n>` when available, and show an honest empty value otherwise.
- Use the same trigger-line source in the overview and the error-detail execution flow.
- Prove contract, API, frontend, and E2E agreement between the overview row and detail highlight.
- Do not invent values for historical rows without `trigger_line`.

## Evidence screenshots

| Production | V2 prototype |
| --- | --- |
| [![Production list trigger time](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-01b-overview-list.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-01b-overview-list.jpeg) | [![V2 prototype list trigger point](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-01b-overview-list.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-01b-overview-list.jpeg) |

Both images are real browser-window captures at `2816×1576`. Production labels the column "trigger time" and shows dates; the prototype labels it "trigger point" and shows `L0`, `L91`, and similar log lines.

## Design authority

- [05 §3.4 Problems and attribution state](../../../plans/fullstack-design/05-api-design.md#34-问题bad_case归因状态与-probe): anchors, metadata, and display fields.
- [05 §3.10 Overview and workspace Sessions](../../../plans/fullstack-design/05-api-design.md#310-总览与空间-session): the temporary semantics of `triggerAt`.
- [05 §4.18 Overview and workspace Session lists](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2): overview list contract.
- [05 §9 Prototype field mapping](../../../plans/fullstack-design/05-api-design.md#9-与原型字段的映射对照): mapping constraints.
- [V2 design §5.1 Metrics and filters](../../../plans/ui-prototype-v2/design-v2.md#51-指标与筛选): list field composition.

## Implementation

- Add nullable `triggerLine` to `BadCaseListItem` in `packages/contracts`; retain `triggerAt` and regenerate OpenAPI/TS.
- Project `bad_cases.trigger_line` or the existing equivalent column through the overview repository/service; never infer it from `createdAt`, event index, or timestamps.
- Update API examples and documentation so `triggerLine` is explicitly nullable and `triggerAt` is no longer used for the trigger-point column.
- Rename the table header to "trigger point" and render `L${triggerLine}` or an em dash, with an accessible description for both states.
- Keep the existing deep link; the detail flow and highlighted line must consume the same line number without another duplicate field.
- Cover populated, null, compatibility, deep-link equality, and contract snapshots in tests.

## Implementation steps

1. Add failing tests showing that the overview cannot distinguish a real trigger line from the temporary `createdAt`.
2. Add nullable `triggerLine` to the shared contract and run `pnpm contract:generate`.
3. Extend the overview projection and cover integer/NULL rows in API tests.
4. Update the table header and renderer, then add component and E2E location assertions.
5. Update the `BadCaseListItem` example, field semantics, and prototype mapping.
6. Run contract, type, API, web, E2E, docs, and flow gates.

## Dependencies and boundary

- Dependencies: m8-04 supplies the overview, m12-02 supplies the live external contract, and m12-07 supplies trace state; all are done.
- Boundary: add only the trigger-line data needed for overview reading and display; do not change trigger computation or execution-flow layout.
- Keep `triggerAt` compatible. A future issue may define a real event timestamp separately.
- Historical NULL values remain NULL with no guessed backfill.

## Verification

```sh
pnpm contract:generate
pnpm contract:check
pnpm test:api -- tests/m8-04-overview
pnpm test:web -- apps/web/src/pages/overview/components/BadCaseTable.test.ts
pnpm test:e2e -- --pattern m12-10
pnpm typecheck
```

- A case with `trigger_line` renders `L<n>` and the error detail highlights the same line.
- A NULL case renders an em dash and returns `triggerLine: null`; `createdAt` is never substituted.
- Existing consumers of `triggerAt` remain compatible and generated contracts have no drift.
- The paginated query has no N+1 and each row receives its own trigger line.
- E2E proves overview, deep link, and detail highlight agree.

## Acceptance

- OpenAPI and TypeScript expose nullable `BadCaseListItem.triggerLine`.
- The overview column is "trigger point", renders log lines when available, and em dashes otherwise.
- No overview row uses `triggerAt` as a trigger point or sort key.
- Overview and detail use one line source for each case, and historical nulls remain unchanged.
- Contract, API, web, E2E, docs, and flow gates are green.

## Gates and CI

- `pnpm contract:generate`, `pnpm contract:check`, `pnpm test:api`, `pnpm test:web`, `pnpm test:e2e`, `pnpm typecheck`, `pnpm lint:docs`, and `pnpm verify:flow`.
- Include cross-database compatibility and at least one real JSONL fixture line-number assertion.

## Non-goals

- Do not change trigger computation, lane DAG, or problem-card layout.
- Do not substitute `createdAt`, array positions, or timestamps for a line number.
- Do not fabricate a bulk backfill for historical NULL rows.
- Do not add list-level filters here.
