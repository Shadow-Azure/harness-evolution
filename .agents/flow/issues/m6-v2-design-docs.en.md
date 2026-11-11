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

- [01-architecture.md §4.4](../../../plans/fullstack-design/01-architecture.md): auth flow and workspace scoping in the overall architecture.
- [05-api-design.md §3.7–§3.10, §4.16–§4.20](../../../plans/fullstack-design/05-api-design.md): workspace/member/credential/ingest/overview/attribution endpoints and DTOs.
- [06-database-design.md §3.10–§3.12, §4.2, §5.3–§5.4, §5.9, §7.5, §9](../../../plans/fullstack-design/06-database-design.md): workspace tables, attribution table (evolved from `probe_reports`), cluster/member tables, candidate table, V2 metrics and migration.
- [07-backend-implementation.md §5.11–§5.15, §8.2.1](../../../plans/fullstack-design/07-backend-implementation.md): seven-step pipeline, potential matcher, attribution cache, workspace service and auth seam.
- [08-frontend-implementation.md §1.4, §4.2, §5.2.1, §6, §7, §9, §10](../../../plans/fullstack-design/08-frontend-implementation.md): space shell, overview, latest-10 list, multi-attribution, four-step wizard, seven-step detail.
- [README decision table D21–D23](../../../plans/fullstack-design/README.md): top-level V2 decisions and V1 freeze semantics.
- [design-v2.md](../../../plans/ui-prototype-v2/design-v2.md): V2 prototype acceptance baseline.

## Implementation

- Merge the V2 design into docs 01–08 by domain instead of adding new addendum docs: 01 boundaries/modules/flows; 02 feature points F21–F27 and acceptance; 03 routes/state/components/directories; 04 modules/integration/config/extensions/tests; 05 DTOs and endpoints; 06 tables and migration; 07 pipeline and implementation; 08 pages and interactions.
- 01: workspace inputs/outputs/non-goals, workspaces service, seven-step execution chain, auth/session and workspace scoping, data-access table, extensions and risks.
- 02: §2.4 (F21–F27 plus changes to five V1 feature points) and §2.5 (V2 acceptance criteria).
- 03: workspace-prefixed routes, space guard, queryKeys carrying `wid`, workspace/overview/multi-attribution components and directories.
- 04: workspaces/overview modules, ingest write boundary, attribution engine placeholder, V2 config keys and test strategy.
- 05: §3.7–§3.10 new DTOs (Workspace/Member/Credential/Ingest/Attribution/Overview); §3.6.2 seven-step payloads; §4.16–§4.20 endpoints; §5 deep links; §8 complete V2 error codes; §9 mapping.
- 06: workspaces/workspace_members/workspace_ingest_credentials; bad_cases.workspace_id; three new evolution_runs columns; attribution and cluster tables evolved in place (`probe_reports → bad_case_attributions`, `probe_clusters → evolution_clusters`, `probe_cluster_probes → evolution_cluster_members`) with `bad_case_analysis` dropped; new `evolution_run_candidates`; §7.5 metrics; §9 migration.
- 07: normalization adds tree_index/triggered_at; seven-step prepare; potential matcher; attribution cache; preview endpoints; workspace service and dependency; auth seam; tests and slicing order.
- 08: routes and redirects; api modules and queryKeys; workspace admin four tabs; latest 10 with enter-to-search; overview page; multi-attribution error detail; four-step wizard; seven-step detail with `stepsSchema` dual track.
- New Agent Note triple `.agents/notes/proposed/feature/2026-11-11-v2-design-docs.*` (decisions and trade-offs).

## Implementation steps

1. Read the V1 design docs and the current implementation to establish the gap baseline (endpoints/tables/services checked item by item).
2. Compare the V1/V2 prototypes and verify UI coverage of the seven requirements.
3. Write the V2 design into docs 01–08 by domain (no new addenda) and fix cross-doc inconsistencies (error codes, columns, `blocked_stage`, admin path rules).
4. Delete the temporary addenda 15–17 and clean up every reference (README/02/09).
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

- Docs 01–08 cover all seven requirements, each with an explicit data model, API contract, and code-change map.
- The overview, wizard, and run declare the same potential-bad-case implementation.
- V1 implemented behavior carries freeze markers, and historical run rendering compatibility (`stepsSchema` dual track) is documented.
- The 05 error-code table covers every V2 code; 06 column definitions agree with references in 05/07; attribution and cluster tables evolve in place rather than being added (consistent with D23).
- The README decision table contains D21–D23; 02 contains F21–F27; the Agent Note bilingual triple has a complete pairing record.

## Gates and CI

- `pnpm verify:flow`: issue triple, state machine, and scope coverage.
- `pnpm lint:docs` / `pnpm verify:docs`: Agent Note pairing and doc gates.
- Docs-only change; no behavioral impact on the API/Web build and test lanes.

## Non-goals

- No V2 feature code or database migration.
- No rewrite of V1 doc bodies (addenda and pointers only).
- No scheduling or slicing decisions for V2 implementation issues here.
