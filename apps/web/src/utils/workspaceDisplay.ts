import type { SessionWorkspace, WorkspaceRole } from "@harness/contracts";

const ROLE_LABELS: Record<WorkspaceRole, string> = {
  global_admin: "全局管理员",
  space_admin: "空间管理员",
  member: "成员",
  viewer: "只读成员",
};

/**
 * Human label for one workspace role.
 * @param role Effective role from auth/session.
 * @returns zh-CN label used by the picker and user menu.
 */
export function workspaceRoleLabel(role: WorkspaceRole): string {
  return ROLE_LABELS[role] ?? role;
}

/**
 * Two-to-three character badge for a workspace card.
 * @param workspace Visible workspace summary.
 * @returns Short mark, preferring an explicit short label.
 */
export function workspaceMark(
  workspace: Pick<SessionWorkspace, "mark" | "name">,
): string {
  const mark = workspace.mark.trim();
  if (mark.length > 0 && [...mark].length <= 4) {
    return mark;
  }
  return [...workspace.name].slice(0, 2).join("");
}

/**
 * Clamp a used/quota ratio to a percentage for the quota bar.
 * @param used Bad cases currently stored in the workspace.
 * @param quota Configured bad-case quota.
 * @returns Integer percentage between 0 and 100.
 */
export function workspaceQuotaPercent(used: number, quota: number): number {
  if (quota <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((used / quota) * 100)));
}

/**
 * Whether the role may manage the workspace or configure its evolution targets.
 * @param role Effective workspace role.
 * @returns True for a global or space administrator.
 */
export function canManageWorkspace(role: WorkspaceRole | undefined): boolean {
  return role === "global_admin" || role === "space_admin";
}
