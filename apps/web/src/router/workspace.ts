import type { SessionWorkspace } from "@harness/contracts";

/** localStorage key remembering the last workspace the person opened. */
export const LAST_WORKSPACE_KEY = "harness.lastWorkspaceId";

/** Default child page inside a workspace: the bad-case overview. */
export const DEFAULT_WORKSPACE_PATH = "overview";

/** Session browser child page; the landing page for legacy session links. */
export const SESSIONS_WORKSPACE_PATH = "sessions";

/**
 * Read the remembered workspace id without throwing in private or test contexts.
 * @returns The stored id, or null when storage is unavailable or empty.
 */
export function readLastWorkspaceId(): string | null {
  try {
    const value = globalThis.localStorage?.getItem(LAST_WORKSPACE_KEY);
    return value && value.length > 0 ? value : null;
  } catch {
    return null;
  }
}

/**
 * Remember the workspace most recently opened by this browser.
 * @param workspaceId Visible workspace identifier.
 * @returns No value.
 */
export function rememberWorkspace(workspaceId: string): void {
  try {
    globalThis.localStorage?.setItem(LAST_WORKSPACE_KEY, workspaceId);
  } catch {
    // Storage can be disabled; the in-session route remains authoritative.
  }
}

/**
 * Forgets the remembered workspace on logout.
 * @returns No value.
 */
export function forgetLastWorkspace(): void {
  try {
    globalThis.localStorage?.removeItem(LAST_WORKSPACE_KEY);
  } catch {
    // Nothing to clean when storage is unavailable.
  }
}

/**
 * Build one path inside a workspace shell.
 * @param workspaceId Workspace route identifier.
 * @param suffix Child path without a leading slash, or empty for the root.
 * @returns App-relative workspace path.
 */
export function workspacePath(workspaceId: string, suffix = ""): string {
  const base = `/workspaces/${encodeURIComponent(workspaceId)}`;
  return suffix ? `${base}/${suffix.replace(/^\/+/, "")}` : base;
}

/**
 * Resolve the workspace for a legacy, workspace-less URL.
 *
 * The remembered workspace wins only while the current user can still see it;
 * otherwise a single visible workspace is unambiguous. Multiple unrelated
 * workspaces must go through the chooser instead of silently picking one.
 * @param lastWorkspaceId Previously remembered workspace id, if any.
 * @param workspaces Workspaces visible in the current auth/session.
 * @returns The workspace to redirect into, or null when the person must choose.
 */
export function resolveLegacyWorkspace(
  lastWorkspaceId: string | null,
  workspaces: readonly Pick<SessionWorkspace, "id">[],
): string | null {
  if (
    lastWorkspaceId &&
    workspaces.some((workspace) => workspace.id === lastWorkspaceId)
  ) {
    return lastWorkspaceId;
  }
  return workspaces.length === 1 ? workspaces[0]?.id ?? null : null;
}

/**
 * Resolve the post-login destination for the current session.
 * @param session Auth store snapshot with visible workspaces.
 * @returns The remembered/single workspace page, or the chooser.
 */
export function defaultLandingPath(session: {
  workspaces: readonly Pick<SessionWorkspace, "id">[];
}): string {
  const workspaceId = resolveLegacyWorkspace(
    readLastWorkspaceId(),
    session.workspaces,
  );
  return workspaceId
    ? workspacePath(workspaceId, DEFAULT_WORKSPACE_PATH)
    : "/workspaces";
}

/**
 * Keep a section but drop resource ids owned by the previous workspace.
 * Session and run identifiers are workspace-scoped, so carrying them across a
 * switch would request a row the new workspace cannot show.
 * @param child Current child path inside the workspace shell.
 * @returns A section path safe to open in another workspace.
 */
export function switchableWorkspaceChild(child: string): string {
  if (child.startsWith("/sessions")) {
    return `/${SESSIONS_WORKSPACE_PATH}`;
  }
  if (
    child.startsWith("/evolution/runs") ||
    child.startsWith("/evolution/cluster")
  ) {
    return "/evolution";
  }
  return child;
}

/**
 * Map one legacy workspace-less path onto the shell.
 *
 * `/` is the retired application root and lands on the new overview, while
 * `/sessions` and `/errors` were session-browser links and must keep opening
 * the Session list instead of being reinterpreted as an overview request.
 * @param workspaceId Resolved workspace identifier.
 * @param path Legacy path such as `/sessions/s-1` or `/evolution`.
 * @returns The equivalent workspace path without the query string.
 */
export function legacyWorkspaceTarget(workspaceId: string, path: string): string {
  if (path === "/") {
    return workspacePath(workspaceId, DEFAULT_WORKSPACE_PATH);
  }
  if (path === "/errors" || path === "/sessions") {
    return workspacePath(workspaceId, SESSIONS_WORKSPACE_PATH);
  }
  return workspacePath(workspaceId, path);
}

/**
 * Whether a path is a legacy workspace-less application path.
 * @param path Current route path.
 * @returns True for `/`, `/errors`, `/sessions/**`, and `/evolution/**`.
 */
export function isLegacyWorkspacePath(path: string): boolean {
  return (
    path === "/" ||
    path === "/sessions" ||
    path === "/errors" ||
    path.startsWith("/sessions/") ||
    path === "/evolution" ||
    path.startsWith("/evolution/")
  );
}

/**
 * Whether the path belongs to the login or forced-change public surface.
 * @param path Current route path.
 * @returns True for login and password-change routes.
 */
export function isAuthSurface(path: string): boolean {
  return path === "/login" || path === "/change-password";
}
