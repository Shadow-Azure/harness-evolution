# Issue #582 Public Badcase Label Routing Implementation Plan

> **For agentic workers:** Execute this plan with `executing-plans`, keep the execution ledger current, and use TDD for every behavior change.

**Goal:** Let each workspace configure the public badcase labels it accepts, assign one public badcase to every matching workspace, and make every later evolution input honor that same workspace boundary.

**Architecture:** Preserve one canonical `bad_cases` row per upstream ID and replace `bad_cases.workspace_id` visibility with explicit `workspace_bad_cases` associations. Public catalog sync validates and projects `meta_data.label`, then reconciles `catalog_label` associations transactionally; direct ingest owns a separate `direct_ingest` association. A workspace label configuration transaction replaces rules and rebuilds historical catalog associations before returning. `WorkspaceReadScope` is the single reusable read boundary for UI, statistics, sessions, quotas, and evolution candidates.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic, Vue 3, TypeScript, Pinia/TanStack Query, Vitest, pytest, SQLite/MySQL.

**Spec:** `plans/fullstack-design/17-workspace-bad-case-label-routing.md`

## Global constraints

- Keep the existing startup + interval public catalog pull and its ID cursor semantics.
- A label is an exact, case-sensitive, non-blank string of at most 128 characters with no surrounding whitespace.
- One label may be configured by multiple workspaces; one canonical case must then be visible in all of them without duplicate counts.
- Missing or invalid upstream labels remain canonical facts but receive no workspace association.
- Existing evolution runs remain immutable; only previews and newly created runs use current associations.
- Existing workspace credential ingest remains supported and is never removed by catalog label changes.
- Every commit and the PR title include `(#582)`.

## Review focus

1. **Visibility leaks:** Tasks 1, 4, and 5 must prove no read path still trusts `bad_cases.workspace_id` for authorization or selection.
2. **Lost or duplicate assignment:** Tasks 1–3 must prove canonical deduplication, multi-workspace fan-out, exact replacement, and transaction rollback.
3. **Cursor/data loss:** Task 3 must prove a catalog page only advances its cursor after facts and associations commit together.
4. **Direct-ingest regression:** Tasks 1 and 4 must prove direct associations survive label edits and quota accounting remains distinct.
5. **Contract/UI drift:** Tasks 2 and 6 must generate contracts and compare the implementation with the V2 prototype and this design.

### Task 1: Add the association data model and migration

**Files:**
- Modify: `apps/api/app/db/models/domain.py`
- Create: `apps/api/alembic/versions/0032_workspace_bad_case_labels.py`
- Modify: `apps/api/tests/db/test_migrations.py`
- Create: `apps/api/tests/db/test_workspace_bad_case_assignments.py`

**Steps:**
1. Write failing migration/model tests for `catalog_label`, both association tables, indexes, foreign keys, and legacy-owner backfill.
2. Run the focused tests and confirm failure for missing schema.
3. Add `WorkspaceBadCaseLabel` and `WorkspaceBadCase` models plus nullable indexed `BadCase.catalog_label`.
4. Add migration 0032 after 0031, including deterministic backfill of all existing `bad_cases.workspace_id` rows as `legacy_owner`.
5. Run SQLite migration and model tests; run the MySQL migration suite when its service is available.
6. Commit: `feat(db): add workspace badcase assignments (#582)`.

### Task 2: Implement label configuration API and atomic historical reconciliation

**Files:**
- Create: `apps/api/app/db/crud/workspace_bad_case_labels.py`
- Create: `apps/api/app/service/workspaces/bad_case_labels.py`
- Modify: `apps/api/app/api/workspaces.py`
- Modify: `apps/api/app/api/schemas.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/api/test_workspace_bad_case_labels.py`
- Create: `apps/api/tests/service/test_workspace_bad_case_labels.py`

**Steps:**
1. Write failing API/service tests for member reads, admin writes, unauthorized writes, validation, sorting, exact replacement, multi-space reuse, historical add/remove, direct association preservation, and rollback.
2. Run the focused tests and confirm the route/service is missing.
3. Implement GET/PUT `/api/workspaces/{workspace_id}/bad-case-labels` with existing workspace membership rules.
4. In one transaction lock/validate the workspace, replace rules, delete only that workspace's `catalog_label` associations, and rebuild them from indexed `bad_cases.catalog_label`.
5. Return the sorted label set and distinct assigned case count only after commit.
6. Run focused tests and commit: `feat(api): configure workspace badcase labels (#582)`.

### Task 3: Route periodic public catalog sync by label

**Files:**
- Modify: `apps/api/app/service/bad_case_catalog_sync.py`
- Modify: `apps/api/app/db/crud/bad_case_sync.py`
- Modify: `apps/api/app/api/bad_case_catalog_sync.py`
- Modify: `apps/api/app/api/schemas.py`
- Modify: `apps/api/tests/m6-16-bad-case-catalog-sync/`

**Steps:**
1. Add failing tests for valid/invalid extraction, exact case matching, two-space fan-out, unassigned labels, retry idempotence, stale association removal, and page rollback without cursor advance.
2. Run the focused catalog suite and confirm the new assertions fail.
3. Validate `items[].meta_data.label` in the service and pass `catalog_label` to persistence.
4. In the existing page transaction upsert facts, replace legacy/catalog associations for touched IDs, fan out to every matching workspace, and update assigned/unassigned/invalid counts before cursor commit.
5. Expose status counts without changing the upstream request contract or scheduler behavior.
6. Run the full catalog sync suite and commit: `feat(sync): route public badcases by label (#582)`.

### Task 4: Preserve direct ingest and distinct quota accounting

**Files:**
- Modify: `apps/api/app/db/crud/bad_case_ingest.py`
- Modify: `apps/api/app/db/crud/workspaces.py`
- Modify: `apps/api/app/db/crud/acquisition_replay.py`
- Modify: relevant tests under `apps/api/tests/`

**Steps:**
1. Write failing tests that direct ingest creates `direct_ingest`, removes same-space legacy ownership, preserves catalog assignments, rejects global-ID ownership conflicts, and counts distinct associations for quota/used.
2. Run focused ingest/quota tests and confirm failures.
3. Update direct ingestion and workspace usage queries to use association rows without double counting.
4. Run focused tests and commit: `fix(ingest): preserve workspace-owned badcases (#582)`.

### Task 5: Move every workspace read and evolution input to one association boundary

**Files:**
- Modify: `apps/api/app/db/crud/read_scope.py`
- Modify: `apps/api/app/db/crud/potential.py`
- Modify: `apps/api/app/db/crud/bad_cases.py`
- Modify: `apps/api/app/db/crud/overview.py`
- Modify: `apps/api/app/db/crud/overview_targets.py`
- Modify: `apps/api/app/db/crud/problems.py`
- Modify: `apps/api/app/db/crud/probe_query.py`
- Modify: `apps/api/app/db/crud/sessions.py`
- Modify: relevant API, service, and DB tests under `apps/api/tests/`

**Steps:**
1. Add failing cross-stack tests showing two workspaces can share one case, unrelated spaces see nothing, all counts are distinct, new evolution candidates follow current configuration, and persisted runs remain resumable after a rule change.
2. Run focused tests and confirm legacy `workspace_id` filters fail the scenarios.
3. Add reusable association `EXISTS`/subquery helpers to `WorkspaceReadScope`.
4. Replace every workspace-scoped badcase selection and join with that helper; retain `bad_cases.workspace_id` only where direct-ingest ownership compatibility requires it.
5. Search for remaining visibility filters and justify or eliminate each occurrence.
6. Run affected API/DB suites and commit: `refactor(api): unify workspace badcase visibility (#582)`.

### Task 6: Add the V2 workspace label management UI

**Files:**
- Modify: `apps/web/src/api/workspaces.ts`
- Modify: `apps/web/src/composables/useWorkspaces.ts`
- Modify: `apps/web/src/views/Admin.vue`
- Create: `apps/web/src/components/admin/WorkspaceBadCaseLabels.vue`
- Modify: `apps/web/src/views/Admin.test.ts`
- Create: `apps/web/src/components/admin/WorkspaceBadCaseLabels.test.ts`
- Modify: `plans/ui-prototype-v2/harness-evolution.html`

**Steps:**
1. Write failing component/view tests for navigation placement, initial loading, sorted chips, Enter/add parity, validation, dirty state, save, assigned count, read-only members, error/empty states, and narrow layout semantics.
2. Run Vitest directly for focused files and confirm failures.
3. Add typed API/composable functions and the `Badcase 类型` tab between `上报接入` and `归因 Skill`.
4. Implement the editor using existing V2 navigation, card, input, button, typography, color, focus, and responsive tokens; do not introduce a parallel visual language.
5. Update the standalone V2 prototype with the same tab and representative populated state.
6. Run focused tests, render actual and prototype UIs, compare them visually, and correct meaningful differences.
7. Commit: `feat(web): manage workspace badcase labels (#582)`.

### Task 7: Synchronize contracts, documentation, and decision record

**Files:**
- Modify generated OpenAPI artifacts under `packages/contracts/`
- Modify relevant `docs/` Chinese/English architecture or API pair
- Create: `.agents/notes/implemented/feature/2026-11-24-workspace-bad-case-label-routing.md`
- Create: `.agents/notes/implemented/feature/2026-11-24-workspace-bad-case-label-routing.en.md`
- Create matching `.i18n.yaml`
- Modify: `.agents/flow/issues/bugfix-evolution-label-allowlist.md`
- Modify: `.agents/flow/issues/bugfix-evolution-label-allowlist.en.md`

**Steps:**
1. Generate the OpenAPI contract and run contract checks.
2. Update current-state documentation in both languages; record the i18n pair.
3. Add an implemented Agent Note documenting the canonical-fact/association decision, rejected alternatives, and consequences.
4. Align the local issue wording with the final architecture and run flow/docs verification.
5. Commit: `docs: record workspace badcase label routing (#582)`.

### Task 8: Full verification, design conformance, and delivery

**Files:**
- Modify only files required by failures or conformance gaps.

**Steps:**
1. Compare implementation line by line with chapter 17 and compare browser screenshots with `plans/ui-prototype-v2/harness-evolution.html`; fix all substantive drift.
2. Run formatters, lint, typecheck, contracts, focused API tests, full Web tests, gates, docs, flow, and the broadest viable API/database suites; document any pre-existing environment-only failures with exact evidence.
3. Use `verification-before-completion`, then create a PR titled with `(#582)` via GitHub CLI.
4. Poll CI with a repository script that repeatedly queries state without calling `sleep`; fix, push, and repeat until green.
5. Run the `pr-review` skill; triage findings and run `pr-review-fix` for every valid finding.
6. Run Computer Use smoke testing and `computer-use-smoke-reporting`; turn defects into PR comments, reproduce with automated tests, fix with `pr-review-fix`, and repeat until clean.
7. Compare final smoke screenshots with the prototype screenshots, upload the report/screens as PR description content or links without committing them, push final commits, and wait for green CI.
8. Merge the PR, confirm issue #582 is closed, and use the flow closure procedure (including a closure PR if required).
