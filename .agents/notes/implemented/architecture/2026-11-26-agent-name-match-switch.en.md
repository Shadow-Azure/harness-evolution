# Agent Note: body hash by default, an explicit switch opens agent name matching

Status: implemented

English | [中文](2026-11-26-agent-name-match-switch.md)

## Problem

Agent evolution targets use `digest:<sha256(normalize_definition_body(body))>` as their version identity, and overview version rows filter on the event's `object_revision`/`definition_hash`. When the body changes between versions, trace snapshots, or runtime injection, the same agent name splits into several rows: the row for the configured ref filters to zero Sessions even though traces with that name clearly exist. The wizard and launch path already associate by "object type + name", while the overview uses hashes, so the two surfaces disagree. Switching everything to name matching would sacrifice version precision for same-name/different-body agents and conflict with the existing "never guess a name from an unknown revision" decision.

## Decision

- Add `HE_AGENT_MATCH_BY_NAME`, a boolean defaulting to `false`; it is read at startup and requires a `harness-api` restart after changes.
- Behavior is unchanged when off. When on, only `object_type=agent` makes `PotentialMatcher.associated_sessions` ignore the supplied `observed_revisions`, and `TargetOverviewService` replaces event-digest versions with one `defaultRef` row.
- The name row's alias set covers the configured ref, the resolved revision, the bare hash, and every historical report `object_version` for that object; historical attributed/nonTarget reports stay on the row, newest per case.
- Report content identity, `targetRevision`, frozen source, run snapshot, cache keys, step-4 reuse/nonTarget statistics, and background binding deduplication still use body hashes; skill/knowledge targets are unaffected.
- `TargetContentResolver`/`TargetDefinitions` are unchanged: launch still needs `AGENT.md` and keeps returning `TARGET_CONTENT_UNRESOLVED` on a read failure; overview name mode still associates by name when resolution fails but does not alter the launch path.
- Historical digest versions and reports stay readable; turning the switch off restores hash behavior with no backfill or rewrite.

## Alternatives considered

- **Global "name first, hash fallback"**: gives up version precision on every object and every read path and breaks the uniform "never guess a name" rule; this switch covers only agent association and version rows.
- **Name-only overview, hash-based wizard**: keeps the two surfaces divergent, so users still see different Session sets in the wizard and the overview; one change in the shared matcher aligns them.
- **A match-mode column on targets or a UI switch**: adds contract, migration, and permission surface, and this is a deployment-time setting better served by `.env`; the issue explicitly rules out columns and form fields.
- **Use name mode for report cache and step-4 statistics too**: reports for same-name/different-body agents would be reused and the report identity and cache scope would change; outside this switch's boundary.
- **Migrate historical version rows**: historical digests and reports remain readable, so backfilling is unnecessary and would rewrite audit facts; the switch can be turned off at any time.

## Consequences

- When on, same-name/different-body agents collapse into one row and Session and potential counts grow; version precision is traded for an explicit opt-in.
- The single overview row still tries to resolve content for ref/commit display; a failed resolution only omits the commit and does not block name association. Launch still fails on the same resolution error.
- `targetRevision` and report caches stay hash-scoped, and turning the switch off restores the prior behavior; existing test assertions do not need to change.
- Operators must restart `harness-api` for the flag to take effect; it adds no OpenAPI, database, or frontend-form surface.
