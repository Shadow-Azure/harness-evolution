# Add a short title to bad_cases

English | [中文](m6-bad-case-title.md)

```yaml flow
kind: issue
id: m6-12
milestone: m6
depends: []
priority: P1
status: backlog
scope:
  - packages/contracts/**
  - apps/api/**
  - apps/web/**
  - fixtures/**
  - reports/**
  - plans/fullstack-design/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/proposed/feature/2026-10-29-bad-case-title.md
github:
  number: 165
  url: https://github.com/Shadow-Azure/harness-evolution/issues/165
```

## Background

The prototype error-detail page renders every problem as two text levels: a short title plus a description body, and both the problem list card and the agent execution graph problem card use the short title as their primary text. The current data model only carries the single long `bad_cases.reason` field, so the error-detail page renders `reason` as the heading with no body level, and an unanalyzed list row can only show "尚未完成归因分析" instead of a readable title. The `BadCase` / `SessionBadCase` contracts and the `bad_cases` table both lack a title field, and the prototype field mapping in [05 §9](../../../plans/fullstack-design/05-api-design.md) never mapped the prototype `finding.title` / `finding.detail` pair to any API field — the short title was lost during design mapping. This is a data-model gap, not a frontend deviation, and it became visible on the error-detail page as soon as real data arrived (`trajectory_payloads` plus reported `bad_cases`).

## Goals

- Add a `title` short-title column to `bad_cases` (required from the external reporter) and narrow `reason` to mean the description body.
- Add `title` to the `BadCase` / `SessionBadCase` contracts and regenerate the OpenAPI document and generated types.
- Render `title` as the heading and `reason` as the body on the error-detail page; use `title` as the primary text on the problem list card and the graph problem card.
- Add `title` as a required field of the upstream problem-report contract and update the fixture demo data.

## Design authority

- [06 database design §4.1](../../../plans/fullstack-design/06-database-design.md): `bad_cases` column definitions; this section is revised together with the new `title` column.
- [05 API design §3.4](../../../plans/fullstack-design/05-api-design.md): `BadCase` DTO and field semantics; adds `title`.
- [05 API design §9](../../../plans/fullstack-design/05-api-design.md): prototype field mapping table; adds the `title` / `reason` two-level text row.
- [Prototype harness-evolution.html](../../../plans/14-15-ui-prototype/harness-evolution.html): the `FindingDescription` title + detail pair is the rendering baseline.
- Where implementation conflicts with the linked sections, the linked sections and the confirmed prototype win.

## Implementation

- Add `title VARCHAR(255) NOT NULL` to `bad_cases`: sync the column in `apps/api/app/db/models/domain.py` and add an alembic migration; existing rows are re-imported by the upstream system per [06 §1.2](../../../plans/fullstack-design/06-database-design.md) or backfilled once (first sentence of `reason`, truncated).
- Add `title` to the BadCase / SessionBadCase schemas in `packages/contracts` and regenerate `openapi.json` plus generated types with `pnpm contract:generate`.
- Expose `title` through the API assembly: repository reads, service read models, and route responses; degraded display keeps using the existing `degraded` mechanism.
- Web: render `title` as the heading plus a new body block for `reason` on the error-detail page; switch the problem list card (`BadCaseList.vue`) and the graph problem card (`BadCaseNode.vue`, card-width measuring in `layout.ts`) to `title` as primary text.
- Fixtures: add `title` to the problem records in `fixture_corpus.py` and the `fixtures/` demo data.

## Implementation steps

1. Contracts first: add `title` to the contracts schemas, run `pnpm contract:generate`, and follow the regenerated types in both stacks.
2. Database: add the column to the domain model and an alembic migration (SQLite batch mode); verify both dialects with `pnpm test:db[:mysql]`.
3. API: expose `title` through repository / service / routes, adding read-model tests and a degraded-path case.
4. Web: two-level rendering on the detail page and the `title` switch on list and graph cards, with component tests.
5. Add `title` to the fixture demo data and run `pnpm fixtures:check`.

## Dependencies and boundary

- Dependencies: none
- Delivery boundary: the `bad_cases` data model, shared contracts, problem read APIs, and problem presentation; no change to the attribution state machine, anchor algorithm, or `probe_reports`; the problem side stays externally written and this service adds no report-write path.

## Verification

```sh
pnpm contract:check
pnpm test:db
pnpm --filter @harness/web exec vitest run src/pages/errors src/components/bad-cases
pnpm fixtures:check
```

- The `BadCase` / `SessionBadCase` contracts contain `title` and `contract:check` passes.
- Every demo problem in the fixture sessions carries a non-empty `title`; the error-detail page shows the short title in the heading and `reason` in the body.

## Acceptance

- `/sessions/{sid}/errors` problem-description tab: the heading shows the `title` short title and the body block shows the full `reason`; the same holds for unanalyzed, non-issue, and issue states.
- The problem list card and the agent execution graph problem card use `title` as primary text while keeping the 150–400px card-width clamping behavior.
- DB schema, OpenAPI, and API responses stay consistent (`pnpm contract:check` passes).
- Legacy or abnormal rows without `title` have a degraded or backfilled path with test coverage.

## Gates and CI

- `pnpm contract:generate` / `pnpm contract:check`
- `pnpm typecheck:api` / `pnpm test:api` / `pnpm test:db[:mysql]`
- `pnpm test` / `pnpm typecheck:web` / `pnpm lint:web`
- `pnpm fixtures:check`
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`

## Non-goals

- No re-verification of "the problem-card-to-skill-trigger edge hidden behind the Agent box": #149/#152 shipped the edge-layer fix; the re-verification on latest main is a separate issue.
- No change to `probe_reports` / `bad_case_analysis` or the attribution state machine.
- No problem-report write API; the problem side stays externally written and the upstream system owns `title` writes.
