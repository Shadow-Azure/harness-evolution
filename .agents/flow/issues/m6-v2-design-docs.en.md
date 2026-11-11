# V2 design docs: workspaces, overview, and attribution in evolution

English | [中文](m6-v2-design-docs.md)

```yaml flow
kind: issue
id: m6-25
milestone: m6
depends: []
priority: P1
status: in-progress
scope:
  - plans/fullstack-design/**
  - .agents/notes/**
  - .agents/flow/**
adr: []
github:
  number: 206
  url: https://github.com/Shadow-Azure/harness-evolution/issues/206
```

## Background

The V2 prototype (`plans/ui-prototype-v2/`) establishes four new capability classes: multi-user login with a reserved auth integration seam, multi-workspace bad-case ingestion with quotas, a workspace overview, and attribution moved into the self-evolution flow. The `plans/fullstack-design` tree still describes the V1 target state: D10 declares a single shared organization with no row-level isolation, evolution input treats external `probe_reports` as its only source, the error detail page carries exactly one attribution per bad case, and nothing defines an overview, workspaces, or an ingest API. V2 implementation issues need linkable design authority (issue body contract: linked sections win on conflict), so the target-state design must land in the doc tree first.

## Goals

- Define the V2 target-state design for three themes: auth integration and workspaces, overview and session list, attribution inside evolution with multi-attribution error detail.
- Cover all seven user requirements: multi-user without registration plus a reserved auth seam; workspaces and roles; per-workspace bad-case ingest with quotas; overview dual view with drill-down; latest-10 sessions with enter-to-search; attribution inside evolution (session association → potential policy → attribution / not-this-object → cache); collapsible multi-attribution error sidebar.
- Keep V1 implemented behavior traceable: freeze markers plus addendum pointers instead of a rewrite.
- Provide code-change maps and a slicing order that follow-up V2 implementation issues can reference directly.

## Design authority

- [15-v2-workspaces.md](../../../plans/fullstack-design/15-v2-workspaces.md): auth integration seam, workspace/member/quota/credential model, ingest API, workspace-scoped migration and permission matrix.
- [16-v2-overview.md](../../../plans/fullstack-design/16-v2-overview.md): overview dual-view metrics, aggregation APIs, latest-10 sessions with enter-to-search.
- [17-v2-attribution.md](../../../plans/fullstack-design/17-v2-attribution.md): seven-step flow, trigger-point coordinates, potential policy, attribution cache, multi-attribution error detail, probe pipeline retirement.
- [README decision table D21–D23](../../../plans/fullstack-design/README.md): top-level V2 decisions and V1 freeze semantics.
- [design-v2.md](../../../plans/ui-prototype-v2/design-v2.md): V2 prototype acceptance baseline.

## Implementation

- Three new addendum docs `15-v2-workspaces.md` / `16-v2-overview.md` / `17-v2-attribution.md` following the 11–14 addendum style (background, data model, API contract, code-change map, tests and acceptance, non-goals, confirmed decisions).
- README: three doc-map rows, decision table gains D21/D22/D23, updated one-line system description and data-boundary block, V2 relationship to repository state.
- 02-features: new §2.4 (F21–F27 V2 feature points plus a change table for five V1 feature points).
- 05-api-design: V2 endpoint block appended to §4; twelve V2 error codes appended to §8.
- 06-database-design: V2 table addendum block in §1 (new tables, added columns, frozen list).
- 01-architecture / 07-backend-implementation / 08-frontend-implementation: boundary revisions (workspace inputs/outputs/non-goals, workspaces service) and V1 freeze notes.
- New Agent Note triple `.agents/notes/proposed/feature/2026-11-11-v2-design-docs.*` (addendum approach and key trade-offs).

## Implementation steps

1. Read the V1 design docs and the current implementation to establish the gap baseline (endpoints/tables/services checked item by item).
2. Compare the V1/V2 prototypes and verify UI coverage of the seven requirements.
3. Write the three addenda (API, table structure, code-change maps, tests included).
4. Revise README/01/02/05/06/07/08 pointers and addendum blocks.
5. Add the Agent Note and re-record the i18n pairing.

## Dependencies and boundary

- Dependencies: none
- Non-goals: no production code changes (`apps/api`, `apps/web`, `packages/contracts`); no V2 implementation issues; no V2 prototype HTML edits.

## Verification

```sh
pnpm verify:flow; pnpm lint:docs
```

- Both green; `verify-flow --diff origin/main` passes scope coverage for this PR's diff.

## Acceptance

- The three addenda cover every one of the seven requirements with an explicit data model, API contract, and code-change map.
- The overview, wizard, and run declare the same potential-bad-case implementation (PotentialMatcher).
- V1 implemented behavior carries freeze markers in 05/06/07/08, and historical run rendering compatibility (steps_schema dual track) is documented.
- The README decision table contains D21–D23; the 02 feature table contains F21–F27; the 05 error-code table contains the new V2 codes.
- The Agent Note bilingual triple has a complete pairing record.

## Gates and CI

- `pnpm verify:flow`: issue triple, state machine, and scope coverage.
- `pnpm lint:docs` / `pnpm verify:docs`: Agent Note pairing and doc gates.
- Docs-only change; no behavioral impact on the API/Web build and test lanes.

## Non-goals

- No V2 feature code or database migration.
- No rewrite of V1 doc bodies (addenda and pointers only).
- No scheduling or slicing decisions for V2 implementation issues here.
