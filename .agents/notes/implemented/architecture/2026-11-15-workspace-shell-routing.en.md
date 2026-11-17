# Agent Note: workspace shell, route guards, and cache isolation

Status: implemented

English | [中文](2026-11-15-workspace-shell-routing.md)

## Problem

m7-04 through m7-07 isolated sessions, bad cases, evolution targets, runs, and SSE on the server, but the web app remained on V1. Its routes were `/sessions/**` and `/evolution/**`, startup restored `refresh` then `me`, query keys started with resource ids, and pages never carried `wid`. The frontend therefore kept calling compatibility endpoints that merge every visible workspace; one session card shared one cache entry across workspaces, switching workspaces had no stable context, and an old deep link could not decide where it belonged.

## Decision

- Route shell: add `/workspaces/:wid` as the parent of the session list, session overview, error detail, evolution list, run detail, cluster preview, and target configuration; `/workspaces` is the chooser. The default child is `overview`.
- Guard: `beforeEach` restores `auth/session` first, sends anonymous users to `/login?redirect=…`, and restricts forced password changes to login/password-change pages. A workspace route requires `wid` to be visible to the current user, otherwise it returns to the chooser with `reason=forbidden`. `/`, `/sessions/**`, `/errors`, and `/evolution/**` are legacy routes resolved as “remembered workspace that is still visible → single visible workspace → chooser”, using `replace`, preserving query/hash, and redirecting once.
- Bootstrap: `tryRefresh` now performs `refresh` plus `GET /auth/session`, reading `user` and `workspaces` from one payload; login and password change re-fetch the same payload so `me` and the workspace list never come from different moments.
- Cache: every `queryKeys` factory starts with `["ws", wid]`; session, bad-case, run, step, event, target, and catalog reads use `/api/workspaces/{wid}/...`. Switching workspaces invalidates the old `["ws", oldWid]` tree and keys `RouterView` by `wid`, so page `ref` state is rebuilt; the switch target drops the previous workspace's `sessionId`/`runId` and keeps only the section.
- Bad-case detail uses the workspace endpoint. The attribution projection comes from the workspace attribution page/detail endpoints; the page compares the returned `sessionId` with the route and treats a mismatch as `409`.
- Top bar: add `WorkspacePicker` (name, role, used/quota, member count); switching keeps the current section and writes the route. The user menu shows the current workspace and role. The sync action invalidates the current `wid` session prefix.

## Alternatives considered

- **Keep global query keys and pass `wid` through page props**: the cache would still hit across workspaces, so the “old query does not hit after switching” acceptance could not hold; rejected.
- **Silently pick the first visible workspace for legacy links**: multi-workspace users would land on the wrong data, which the design forbids; unresolved links go to the chooser.
- **Read `route.params.wid` and build URLs in every page**: links and cache keys would keep missing `wid`; use `useWorkspaceId`, `workspacePath`, and the query-key factory.
- **Keep passing `sessionId` to the workspace bad-case endpoint for ownership**: that endpoint ignores it, so a cross-session read would silently succeed; compare the returned `sessionId` in the page instead.
- **Keep the full child path when switching**: `/sessions/:sid` belongs to the old workspace and would only 404 in the new one; keep the section only.

## Consequences

- The `used` aggregate in `auth/session` reads the externally bootstrapped `bad_cases` table; a fresh deployment must initialize that schema first or the workspace shell stalls at login.
- The landing page is the workspace overview; `DEFAULT_WORKSPACE_PATH` and the guard target stay aligned.
- Attribution and probe compatibility endpoints still filter by the union of visible workspaces; V2 pages use workspace attribution endpoints, and retirement lives in [compatibility.en.md](../../../../docs/compatibility.en.md).
- If a visible workspace is removed while a browser still sits on its URL, the guard returns to the chooser; a `404 WORKSPACE_NOT_FOUND` from the API renders the page error state instead of silently switching.
- The four-step wizard uses the workspace preview endpoints; `probes/query` remains compatibility-only and never enters a V2 page.
- `/auth/session` returns at most 200 visible workspaces; above that cap the guard treats an unlisted `wid` as invisible, and fully supporting very large workspace sets needs a server-side lookup.
- The legacy route layer stays until V3; before removing it, follow the checklist in [compatibility.en.md](../../../../docs/compatibility.en.md) and confirm bookmarks, E2E, and external links no longer use workspace-less paths.
