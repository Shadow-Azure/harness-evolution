# Assign public bad cases to workspaces by label

English | [中文](bugfix-evolution-label-allowlist.md)

```yaml flow
kind: issue
id: bugfix-48
milestone: bugfix
depends: []
priority: P2
status: backlog
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - .agents/**
  - docs/**
adr: []
github:
  number: 582
  url: https://github.com/Shadow-Azure/harness-evolution/issues/582
```

## Background

Production bad cases are reported to one public repository. The platform periodically pulls mixed categories from that source, and `items[].meta_data.label` identifies each category. Workspaces configure accepted labels; the same label may be configured by multiple workspaces, so one matching bad case must be available to all of them.

## Goals

Add a Badcase types tab to workspace management and use its rules to build a many-to-many assignment between public bad cases and workspaces. Browsing, Sessions, statistics and evolution then share that assignment boundary.

## Design authority

Follow the [evolution domain](../../../plans/fullstack-design/02-features.md#22-自进化域) and public catalog sync design. Update the relevant design chapter and an Agent Note during implementation.

## Problem, investigation and root cause

1. apps/api/app/third_party_api/bad_case_query/http.py calls GET {HE_BAD_CASE_QUERY_BASE_URL}/bad-cases with bad_case_id, offset and limit, without label parameters.
2. models.py in that directory declares BadCaseItem.meta_data as Any | None without a label contract. This supports carrying labels but does not prove their presence or type in live responses.
3. apps/api/app/service/acquisition/bad_case_catalog_sync.py preserves meta_data but upserts public records directly into bad_cases without parsing labels or assigning workspaces.
4. bad_cases.bad_case_id is a global primary key and each row has one workspace_id. It cannot represent one public bad case assigned to several workspaces, while copying rows conflicts with the global key.
5. Browsing, Sessions, statistics and PotentialMatcher.associated_sessions use bad_cases.workspace_id. Evolution-only filtering would create inconsistent boundaries and still cannot expose one case to several workspaces.
6. apps/web/src/pages/workspaces/Admin.vue has no label-rule UI, while the backend lacks rule persistence, reconciliation and unassigned-data observability.

The root cause is coupling the public bad-case fact to a single workspace_id, plus the absence of a many-to-many label assignment rule and post-sync allocation process. Findings are static code analysis; production data was not queried. Confirm label shape and completeness with sanitized samples.

## Implementation

The sole recommended solution is to keep bad_cases as the public fact table, add workspace label rules and a badcase-workspace relation, and have sync plus reconciliation maintain the relation. Every workspace read path uses that relation.

- Add workspace_bad_case_labels(workspace_id, label), unique by the pair. One label may map to many workspaces. Add a manually managed Badcase types tab; global and workspace administrators may write, with server-side authorization.
- Add workspace_bad_cases(workspace_id, bad_case_id, assignment_source, label, assigned_at), unique by workspace, case and source, where assignment_source is legacy_owner / direct_ingest / catalog_label and label only appears on catalog_label rows. Keep one public fact in bad_cases and stop using its single workspace_id as ownership. Migrate existing workspace_id values into legacy_owner relations and remove legacy-field dependencies, for SQLite and MySQL.
- Sync validates meta_data.label, upserts the public fact, finds every workspace accepting that label, and idempotently writes all relations. One bad case can belong to many workspaces while its source record remains singular.
- Saving rules starts a controlled reconciliation over local public facts for affected labels. Adding a rule backfills history; removing it deletes only that workspace's live relations. No cursor rewind or upstream refetch is required, and persisted inputs of existing runs remain intact.
- Browsing, Sessions, statistics, quota counts, attribution candidates and evolution all constrain through workspace_bad_cases. Existing target, version, time and evidence filters still intersect with this boundary.
- Recommend nonempty, case-sensitive exact string labels. Reject blank and surrounding whitespace. Preserve records with missing, null, empty or non-string labels but leave them unassigned, with invalid/unassigned sync counters; never put them in a default workspace.
- When upstream changes a historical label, remove relations produced by the old label and rebuild from the new label within a transaction or recoverable job boundary.

## Implementation steps

1. Verify sanitized label samples and fix the label contract, migration design and Agent Note.
2. Implement both relation tables, migrate current workspace_id data, add the authorized rule API and generate shared contracts.
3. Update public sync and reconciliation, including invalid/unassigned observability.
4. Move every workspace read path to the relation and complete UI and cross-stack verification.

## Dependencies and boundary

No upstream filtering API is required; one public source and one global cursor remain. Actual label type verification is an implementation prerequisite. This issue owns workspace assignment and all consuming read paths, not upstream data production.

## Verification

Use public fixtures with A/B, missing, null and numeric labels. Workspace one accepts A; workspace two accepts A/B. Run pnpm test:api:serial, pnpm test:db, pnpm test:db:mysql, pnpm test and pnpm test:e2e. Verify that A is stored once and related to both spaces, B only to space two, and invalid/unconfigured labels remain unassigned. Adding and removing rules reconciles history; browsing, statistics, Sessions and full/cluster_only evolution see identical sets; retries create no duplicates and existing runs still resume.

## Acceptance

- One label can serve several workspaces; each source bad case is stored once and related to every matching workspace.
- Rules persist with authorization; additions and removals deterministically reconcile history and unauthorized writes are rejected.
- Missing, invalid and unconfigured labels enter no workspace and have observable counts.
- Browsing, Sessions, statistics, quotas and evolution share the same set; sync and reconciliation are idempotent and existing runs remain recoverable.

## Gates and CI

Implementation runs pnpm contract:generate, pnpm contract:check, pnpm typecheck, pnpm typecheck:web, pnpm lint:api, pnpm lint:web, pnpm test:db, pnpm test:db:mysql and the behavior tests above. CI includes new cases and maintains at least 80% coverage. Documentation runs pnpm record:i18n -- .agents/flow/issues/bugfix-evolution-label-allowlist.md, pnpm verify:flow and pnpm lint:docs. Issue creation does not claim product acceptance tests passed.

## Non-goals

No upstream changes, public fact deletion, label inference or completion, label dictionary, or retrospective modification of existing run inputs.

