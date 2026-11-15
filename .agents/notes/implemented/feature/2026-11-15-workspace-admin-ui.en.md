# Agent Note: workspace admin tabs and one-time credentials

Status: implemented

English | [中文](2026-11-15-workspace-admin-ui.md)

## Problem

m7-05 already exposed the full API for workspace creation and quota, member roles, self-appointment as space administrator, and ingest credentials, and m7-08 moved every business page under the `/workspaces/:wid` shell. Management still lived at the `/api` layer: a global administrator had to call endpoints by hand to create a workspace, and a space administrator had to do the same to adjust quota or rotate a credential. Credentials are especially risky because the list endpoint never returns plaintext; if the creation response stays in component state, a stale render can leak the secret into caches or logs. The UI also has to separate “server authority” from “hidden entries”: hiding a button is only experience, while the real 403/404 still comes from the API.

## Decision

- Add `/workspaces/:wid/admin` and `pages/workspaces/Admin.vue` with four tabs matching the prototype: `spaces` (workspaces and quota), `members` (members and roles), `ingest` (ingest access), and `auth` (authentication access). The active tab lives in `?tab=` so it is deep-linkable.
- Entries follow the effective role: the top-bar `#tn-admin` item and the workspace picker’s “空间设置 →” footer appear only for `space_admin` / `global_admin`. Members and viewers may still open the page, but see a “只读” badge, no write buttons, and an ingest tab that renders an explanation card without requesting credentials. A `space_admin` row is locked to a read-only badge for space administrators and cannot change role or be removed.
- A global administrator sees the full workspace table and “创建工作空间”; a space administrator sees only the current workspace’s quota, administrators, and “调整额度 / 管理成员”. The creation dialog defaults the initial space administrator to the current account; candidates come from `GET /api/users` (global administrator only, creation dialog only, no separate user-directory page).
- The credential creation response is stored only in the component-local `createdCredential`; closing the dialog clears it and removes it from the DOM. The curl example shows the `<workspace credential>` placeholder while no plaintext is readable. Rotation creates the new credential first, shows its plaintext once, and lets the user revoke the old one afterwards so upstream ingest never stops.
- Cache keys gain `["ws", wid, "admin", "members" | "member-candidates" | "credentials"]`. Workspace/member writes invalidate the admin prefix, `["ws"]`, and `["auth","session"]`; credential rotation invalidates only credentials. Every request still goes through `api/http.ts` for Bearer and 401 refresh.
- Contracts only add the `UserListResponse` export; management payloads reuse the generated `@harness/contracts` types so frontend and backend fields cannot drift.

## Alternatives considered

- **Inline the creation form inside the spaces tab**: a dialog gives a clear close path that clears plaintext and form state, and matches the prototype `WorkspaceFormDialog`; rejected.
- **Let members/viewers request credentials and only hide buttons**: that returns 403 and pollutes the global error surface; disable the query by role and render the read-only explanation.
- **Type user ids when creating a workspace**: error-prone and needs a global directory; use the administrator-only `GET /api/users` for initial administrators without adding a directory page.
- **Keep credential plaintext in Pinia or the query cache**: devtools, persistence, and invalidation can carry it away; use a component-local `ref` that is dropped on close.
- **Let the frontend decide whether writes are allowed**: the server remains the only authority; the frontend only controls entry visibility, and m7-05 tests cover direct 403/404 calls.

## Consequences

- The admin page adds two request chains (`GET /api/workspaces` and `GET /api/users`); a global administrator pays one extra user-list read on first entry, while a space administrator does not request the user list.
- Members and viewers can open the page and read the current workspace, but the `ingest` tab does not request credentials, so they see only the endpoint and not sensitive credential state.
- Credential plaintext exists only inside the creation dialog; if the user closes it without copying, the credential must be rotated again, which is the intended “show once” boundary.
- Workspace creation depends on `GET /api/users` returning every account; at large account counts that endpoint has no paging and will need server-side search or pagination.
- Hidden entries cannot replace server checks; the m7-05 role matrix stays the acceptance baseline, and every new write entry needs an API 403 test.
- Admin dialogs rely on `unplugin-vue-components` for on-demand style injection; explicitly importing Element Plus components bypasses the style side effect and makes the dialog lay out as a static full-width block. New dialogs follow the global-component convention instead of importing `ElDialog` / `ElForm` in script.
