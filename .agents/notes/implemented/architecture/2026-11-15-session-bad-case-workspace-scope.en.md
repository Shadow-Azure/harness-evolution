# Agent Note: Workspace-scoped Session and bad-case read paths

Status: implemented

English | [中文](2026-11-15-session-bad-case-workspace-scope.md)

## Problem

m7-03 put a workspace gate in front of every request and m7-05 added workspace administration and ingest credentials, but Session and bad-case reads still only asked "does this row exist". A browser could swap a `sessionId` or `badCaseId` and read problems reported by another workspace; when two workspaces reported the same root session, each also saw the other's bad cases. Trace tables are global by design and do not carry `workspace_id`, so "which workspace owns this Session" can only be derived from bad-case ownership, not patched in the frontend router.

## Decision

- Add `WorkspaceReadScope` (`db/crud/read_scope.py`) as the single visibility definition: `for_workspace(wid)` pins one already-authorized workspace, `for_user(userId)` expands to a membership subquery, and `all_workspaces()` is only for the global administrator. There is intentionally no default constructor, so a forgotten scope cannot silently widen a read.
- Derive the Session set from `bad_cases.workspace_id`: list filters, overview, Agent tree, and problem lists first require `session_families.id IN (the scope's bad_case_session_id)` and then apply their existing filters. Unprojected Sessions disappear from lists and answer `404 SESSION_NOT_FOUND` on direct access; an invisible workspace answers `404 WORKSPACE_NOT_FOUND`, never distinguishing "exists but unauthorized".
- Add V2 routes: `GET /api/workspaces/{wid}/sessions`, `/{sid}`, `/{sid}/tree`, `/{sid}/bad-cases`, and `/bad-cases/{badCaseId}`, all behind `require_workspace_role(wid, viewer)`. After pinning the workspace, one shared root session exposes only that workspace's bad cases, and a problem outside it answers `404 BAD_CASE_NOT_FOUND`.
- Keep every V1 route path and DTO unchanged and only switch visibility to the union of the caller's visible workspaces: membership rows for normal users, everything for the global administrator. `GET /api/workspaces/{wid}/sessions` still returns `{items}` with V1-style filtering in this slice; latest-ten `total/pendingSessions` semantics belong to m8-02.
- `probe_reports` has no `workspace_id` yet (the 0015 attribution migration has not landed), so probe reads inherit the Session boundary instead: `/api/probes/{id}` and `/api/sessions/{sid}/probes` both require a projected Session and do not invent a workspace column.
- `bad_cases` is an externally bootstrapped table and may not exist before the first report. Repositories probe for it on first read and return an empty projection when it is missing (empty lists, 404 on direct access) instead of failing the whole Session page; a positive probe is cached per repository so later reads do not repeat the metadata query.

## Alternatives considered

- **Add `workspace_id` to trace tables**: one root session can be referenced by several workspaces, so the column needs ownership arbitration inside the sync pipeline and would split the global normalization; the design deliberately treats a Session as a projection rather than an owned entity.
- **Repeat `IN (SELECT …)` in each query**: six read paths (list, overview, tree, problems, probes) would each need the predicate, and one omission is an authorization hole; `WorkspaceReadScope.condition()` makes every path declare its scope once.
- **Answer 403 for invisible workspaces and 404 only for Sessions**: 403 reveals that a workspace exists, letting users enumerate workspace ids; one 404 matches the design's "invisible workspace" rule.
- **Drop the legacy routes and keep only V2**: existing pages and E2E still call the unprefixed paths; freezing one version with workspace filtering is lower risk than changing both sides at once.
- **Also add latest-ten `total/pendingSessions` here**: that duplicates m8-02's filter semantics and its acceptance redefines search as an exact root-session-id lookup; this slice only adds the workspace constraint.

## Consequences

- A Session with no bad cases no longer appears in lists and cannot be opened directly. That is the direct consequence of "the workspace Session set is the projection of workspace bad cases" and means reporting or catalog sync must happen before a conversation is visible.
- The global administrator still sees every workspace on legacy endpoints, equivalent to no filter; a space admin sees only joined workspaces, and membership changes apply on the next request.
- Each legacy read adds one membership subquery (`workspace_members` is keyed toward `(workspace_id, user_id)`), while tree and problem reads remain in a single snapshot transaction.
- Probe boundaries stop at "the Session is visible"; once 0015 adds `probe_reports.workspace_id`, they should tighten to workspace ownership.
- `WorkspaceReadScope` does not enforce mutual exclusivity of its three modes at runtime; every new read path must select one explicitly and may not pass `None` through as "everything".
