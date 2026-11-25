# Bad Case sync-source factory design: base class + factory + ClaudeUpstream subclass

English | [中文](bugfix-bad-case-sync-source-factory-design.md)

```yaml flow
kind: issue
id: bugfix-42
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - plans/fullstack-design/16-bad-case-sync-source-factory.md
  - plans/fullstack-design/README.md
  - .agents/**
adr:
  - ../../notes/implemented/architecture/2026-11-23-bad-case-sync-source-factory.md
github:
  number: 548
  url: https://github.com/Shadow-Azure/harness-evolution/issues/548
```

## Background

Bad cases have two independent source lines: API reporting (workspace credential `POST /api/workspaces/{wid}/bad-cases`) and the global source (upstream API sync: `HttpBadCaseCatalogSource` catalog paging plus `HttpSessionQuerySource` two-endpoint trace backfill). The global line has a structural gap today: two unrelated HTTP clients sit side by side with no shared parent class or factory; `BadCaseRootSyncService._sync_root()` switches between the report/global fetch paths with an inline if/else (bad_case_sync.py:303-447); main.py assembles them in two nearly copied procedural if blocks (main.py:270-325); the global line's payload runtime_key falls through to the hard-coded default `"claude-code"` (`_payload()`); and the catalog sync's `on_duplicate_key_update` unconditionally overwrites the upstream fields of an already reported row with the same id (bad_case_catalog_sync.py:24-38,295-305), so "an already reported case is not synced again" holds only in a half sense. The feature request: turn the global line into factory + base class + subclass, route both bad-case fetching and session fetching through base-class trigger calls implemented by subclasses, enable it only once .env is configured (off when unconfigured), let the factory instantiate the subclass from .env, encapsulate every related change inside the subclass, and reuse the existing Session parsing base class/subclass for session handling while adding a new subclass implementation.

## Goals

- Deliver one linkable design chapter `plans/fullstack-design/16-bad-case-sync-source-factory.md` (also registered in the `plans/fullstack-design/README.md` index) covering: the gap between the current state and the target, the interface design of the `BaseBadCaseSyncSource` base class / `BadCaseSyncSourceFactory` factory / `ClaudeUpstreamBadCaseSyncSource` subclass, the decoupling derivation, and step-by-step JSON comparisons of the catalog-sync and root-sync data flows.
- Pin four design decisions: ① code identifiers use the `BadCaseSync*` naming family (not `Global*`); ② the report line and the global line switch independently (the global switch is read only by the factory at assembly time, and the four switch combinations never affect each other); ③ an already reported bad case is never overwritten by the global catalog sync (writer-ownership rule plus a skipped counter); ④ the if/else in `_sync_root` collapses into a "frozen snapshot → unified fetcher" data mapping (`fetch_session()` is isomorphic to the existing `SessionSourceFetcher` protocol).
- Serve as the design authority for follow-up implementation issues: when an implementation conflicts, the linked sections of this document win.

## Design authority

- [§1 Current-state inventory](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s1): the real chains of the two sources, the component split of the global line, and per-file evidence (bad_case_sync.py / session_query / bad_case_query / main.py line numbers).
- [§2 Gap analysis](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s2): a per-item gap verdict for the seven target requirements against the current state.
- [§3 Target design](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s3): the three new module pieces (base class/subclass/factory), the .env switch `HE_BAD_CASE_SYNC_PROVIDER` with the switch matrix, the `fetch_session` template method with signature alignment, and the de-duplication rule.
- [§4 Decoupling derivation](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s4): a change-locality comparison across four upstream-change scenarios.
- [§5 Catalog-sync data flow](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s5): the step-by-step JSON of `fetch_bad_case_page` → `BadCasePage` → `CatalogCaseRow` → de-duplication skip → persistence.
- [§6 Root-sync data flow](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s6): the step-by-step JSON of source routing/freezing → `fetch_session` → `SessionInfo` → payload → replay parsing.
- [§7 Compatibility and risks](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s7): the `SessionSourceSnapshot` extension (`extra="forbid"`), behavioral compatibility, the test blast radius, and the rollout order.

## Implementation

- Add `plans/fullstack-design/16-bad-case-sync-source-factory.md` (chapter 16, a pure design document and the only deliverable of this issue) plus its row in the `plans/fullstack-design/README.md` index.
- Add the Agent Note trio `.agents/notes/proposed/architecture/2026-11-23-bad-case-sync-source-factory.*`: record the three decisions—naming (`BadCaseSync*` over `Global*`), if/else collapse (over keeping the skeleton), and catalog-sync de-duplication (over unconditional overwrite)—together with the rejected alternatives.
- Add this issue's trio, filed under the bugfix milestone (the standing bucket) without opening a new milestone.

## Implementation steps

1. Read through `service/acquisition/bad_case_sync*.py`, `third_party_api/session_query|bad_case_query|session_source/`, and the `main.py` assembly section to confirm current behavior (including upsert overwrite semantics and frozen routing).
2. Produce the design document: gap analysis → base class/subclass/factory design → decoupling derivation → JSON comparison of the two data flows → compatibility risks and rollout order.
3. Revise per the user's feedback rounds: independence of the two lines with the switch matrix, per-root source routing wording, de-duplication of reported cases, the `BadCaseSync*` naming, and filing under the bugfix milestone.
4. Write the Agent Note, re-record the i18n pairing, pass the flow and documentation gates, then open the PR after `flow:sync` backfills the number.

## Dependencies and boundary

- Dependencies: none (pure design; no production code changes).
- Non-goals: no code changes in `apps/api`, `apps/web`, or `packages/contracts`; no implementation issue; no new database migration; no new milestone.

## Verification

```sh
pnpm verify:flow; pnpm lint:docs
```

- All green; `verify-flow --diff origin/main` passes scope coverage for this PR's diff.

## Acceptance

- The design document covers every feature requirement: the factory instantiates the subclass from .env, off when unconfigured, fetching goes through base-class triggers with subclass implementations, changes are encapsulated in the subclass, and session handling reuses the existing base/subclass/factory while leaving a hook for a new subclass.
- The document contains step-by-step descriptions of both data flows: each step gives the handling class.function and its input/output JSON shapes.
- The document states the independence of the two lines (the four switch-matrix combinations), the writer ownership and skip rule for already reported bad cases, and the if/else collapse for `_sync_root`.
- The Agent Note pairing is complete in both languages and records the three key decisions and the rejected alternatives.

## Gates and CI

- `pnpm verify:flow`: the issue trio, the state machine, and scope coverage.
- `pnpm lint:docs` / `pnpm verify:docs`: Agent Note pairing and the documentation gates.
- Documentation-only change; no behavior change in the API/Web build and test lanes.

## Non-goals

- Do not implement the `bad_case_sync_source/` module or any sync-service refactor.
- Do not change the API report line's behavior; do not touch the DB snapshot `kind="global"` data label.
- Do not decide the scheduling or split of implementation issues within this issue.
