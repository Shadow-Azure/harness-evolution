# Agent Note: Workspace ownership for evolution resources and ticket boundaries

Status: implemented

English | [中文](2026-11-15-evolution-workspace-scope.md)

## Problem

m7-02 added `workspace_id` to `evolution_targets`, `evolution_runs`, and `evolution_run_events`, and changed target uniqueness to include the workspace. Reads and services still behaved globally: target lists returned every space, the same object name could not be configured twice, and run list, detail, retry, steps, and events looked runs up by id alone. SSE tickets only checked that a run existed and was active. Any logged-in user who obtained another space's run id could therefore read its detail, fetch events, or subscribe to SSE. Wizard preview and run preparation resolved bad cases by object name globally, pulling other spaces' data into a run. Conflict detection still matched the old single-column constraint name, so a duplicate object surfaced as a 500.

## Decision

- `workspace_id` is the single ownership column for evolution resources; targets, runs, and events all derive visibility from it, with no mapping table. Target uniqueness is `(workspace_id, object_type, object_name)`. Every repository read and write accepts an optional `workspace_ids` filter; omitting it means an explicit global scope reserved for global-administrator paths.
- V2 routes live under `/api/workspaces/{wid}/evolution/**`: targets, runs, steps, run events, retry, cluster previews, launch, and the per-space target/model catalogs. Reads require `viewer`; writes (target CRUD, launch, cluster preview, retry) require `space_admin`; global administrators keep the existing passthrough. The path workspace also constrains resource ownership, and cross-space resources return 404 so existence is not disclosed.
- Legacy unscoped routes remain for one version and filter by the caller's visible spaces: a global administrator is unscoped, everyone else passes `WorkspaceService.visible_ids`. Legacy target writes stay global-admin only; legacy launch and retry resolve the target or run workspace and then enforce `space_admin`, so members and viewers cannot write through the old paths.
- Legacy launch carries no workspace and resolves `(object_type, object_name)` within visible spaces. A single match is used; multiple matches prefer the default workspace, and a remaining ambiguity returns `409 TARGET_NOT_CONFIGURED` rather than guessing across spaces.
- The run write path snapshots the workspace from its target: run creation stores `workspace_id`, probe-hit queries and preparation associate with `(run.workspace_id,)`, and event appends inherit the workspace from the run row. Callers never supply the space separately, so the two cannot diverge.
- `POST /api/events/ticket` accepts an optional `workspaceId`. When present, membership in that space is proven first and every topic run must belong to it. When absent, each run's workspace membership is checked, preserving legacy clients without weakening the boundary. Every failure maps to `401 TICKET_INVALID`, whether the space is missing, invisible, or the run is not subscribable.
- Catalogs use the same space view: legacy `/api/catalogs/**` filters by visible spaces, and V2 adds `/api/workspaces/{wid}/catalogs/**`. The model catalog aggregates `agents.model` from sessions projected through that space's bad cases instead of returning every model in the database.

## Alternatives considered

- **Filter legacy endpoints only and add no V2 routes**: m7-08's workspace shell and later wizard are already designed around `/workspaces/{wid}/evolution/**`. Deferring the routes would force a later issue to revisit the API and contracts, and legacy routes have no workspace context to express space-admin writes.
- **Restrict legacy launch and retry to global administrators**: the cheapest implementation, but it would break existing space administrators on V1 pages and contradict the acceptance that space administrators act on their own space.
- **Authorize SSE by run id alone**: an unguessable id is not authorization; a leaked link would still subscribe. A ticket must carry provable space context. Making `workspaceId` mandatory would break the old client, so it stays optional with a per-run fallback on the server.
- **Trust a caller-supplied workspace for events**: event space must derive from the run row; otherwise one bad caller could write into another space and affect ticket filtering.
- **Return 403 for cross-space resources**: that discloses existence and conflicts with m7's shared invisible-space 404 semantics.

## Consequences

- Existing integration tests that expected members and administrators to see identical lists no longer hold: members need a membership row. Migration added a default-space viewer row only for users that existed then; users created later are added explicitly by a space administrator.
- Legacy unscoped paths are a compatibility layer whose writes stay global-admin only. Space administrators and the frontend use V2 paths. Legacy launch rejects an object name configured in multiple spaces instead of choosing a space for the caller.
- The event table already had its space column, migration, and index; this slice only adds the write and ticket checks, with no new migration.
- Later knowledge-base objects and attribution previews should follow the same pattern: space on the resource, `{wid}` in the route, and a space proof on the ticket. The optional `workspaceId` compatibility branch can become required once the old frontend retires.
