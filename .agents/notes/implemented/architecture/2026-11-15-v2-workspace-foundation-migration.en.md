# Agent Note: One revision for the V2 workspace foundation

Status: implemented

English | [中文](2026-11-15-v2-workspace-foundation-migration.md)

## Problem

V2 permissions, quotas, and attribution all need a workspace scope, but V1 `bad_cases`, `evolution_targets`, `evolution_runs`, and `evolution_run_events` have no workspace column and users only carry a global role. The migration must keep existing rows visible, keep V1 writes working until the workspace API lands, and give SQLite test databases and MySQL production databases the same semantics.

SQLite has limited `ALTER TABLE` support. Rebuilding a parent table to add a foreign key or replace a unique key runs with `PRAGMA foreign_keys=ON` and triggers `ON DELETE CASCADE` / `SET NULL`, silently rewriting child rows—exactly the loss this migration must avoid.

## Decision

- One Alembic revision, `0014`, creates `workspaces`, `workspace_members`, and `workspace_ingest_credentials`, adds `auth_provider` / `external_subject` plus a unique index to `users`, and adds `workspace_id`, indexes, and backfill to the four business tables.
- The default workspace is `ws-default`, with `quota = COUNT(bad_cases) + 50` and the name “默认空间”. Every existing user joins it as `viewer`; global admins still pass through by `users.role` and do not depend on a membership row.
- `workspace_id` carries `DEFAULT 'ws-default'`: until the workspace API lands, V1 catalog sync, fixtures, and internal writes keep landing in the default workspace; callers from m7-03 onward own explicit scoping. This default is a transition rule, not a substitute for isolation.
- MySQL gets workspace foreign keys on `bad_cases`, `evolution_targets`, and `evolution_runs`; `evolution_run_events.workspace_id` stays a design-specified audit redundancy without a foreign key. SQLite does not rebuild parent tables, so it keeps `NOT NULL`, the default, and indexes but no workspace foreign key; the workspace service must enforce the same rules in code.
- `evolution_targets` uniqueness moves from `(object_type, object_name)` to `(workspace_id, object_type, object_name)`. The SQLite key change rebuilds only that table and backs up plus restores `evolution_runs.target_config_id`, so `SET NULL` cannot rewrite run snapshots.
- `test:db` covers empty upgrade, repeated upgrade, legacy backfill, and cross-workspace uniqueness; the CI `test:db:mysql` lane verifies the MySQL empty upgrade.

## Alternatives considered

- **Rebuild every parent table on every dialect to add foreign keys**: SQLite would cascade or null child rows, irreversibly damaging run and analysis data; rejected.
- **Leave `workspace_id` nullable and tighten after the workspace API lands**: legacy rows would stay invisible and quota or deduplication queries would need NULL handling everywhere; rejected.
- **Declare workspace foreign keys on the ORM models**: the external `bad_cases` table is bootstrapped from model metadata in the fixture path, and a cross-MetaData foreign key cannot resolve there; foreign keys stay migration-owned while models express columns and indexes.
- **Move attribution tables into `0014`**: multi-attribution, cache keys, and `probe_reports` semantics belong to the later attribution issue; mixing them would blur the rollback boundary and acceptance.
- **Read the default workspace ID from configuration in the migration**: application configuration is not yet the schema source of truth; fix `ws-default` now and unify through configuration wiring later.

## Consequences

- Write paths from m7-03 onward must pass the workspace explicitly. Until then, a missing value silently enters the default workspace—a known transition risk.
- The missing SQLite workspace foreign key only affects tests and local databases; MySQL production has the constraint. The workspace service must keep the same invisible-workspace 404 rule.
- The attribution migration (`probe_reports.workspace_id` and friends) is the next revision; this revision does not promise multi-attribution queries.
- The default workspace name and `mark` are migration-generated values; the management UI can show and rename it like any other workspace.
