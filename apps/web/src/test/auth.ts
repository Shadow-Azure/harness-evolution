import type { PublicUser, SessionWorkspace } from "@harness/contracts";

import { useAuthStore } from "../stores/auth";

/** Workspace used by component tests that mount a workspace shell page. */
export const TEST_WORKSPACE_ID = "ws-test";

/**
 * One visible workspace summary with deterministic aggregates.
 * @param overrides Fields replaced by the test.
 * @returns Session workspace payload accepted by the auth store.
 */
export function testWorkspace(
  overrides: Partial<SessionWorkspace> = {},
): SessionWorkspace {
  return {
    id: TEST_WORKSPACE_ID,
    name: "测试空间",
    mark: "WT",
    role: "global_admin",
    quota: 60,
    used: 4,
    memberCount: 3,
    spaceAdminCount: 1,
    ...overrides,
  };
}

/**
 * Put an authenticated user with a visible workspace into the active Pinia.
 * @param user Public user installed in the auth store.
 * @param workspaces Workspaces visible to the session.
 * @returns The configured auth store.
 */
export function signInWithWorkspace(
  user: PublicUser = {
    id: "u-1",
    username: "admin",
    displayName: "管理员",
    role: "admin",
    mustChangePassword: false,
  },
  workspaces: SessionWorkspace[] = [testWorkspace()],
) {
  const auth = useAuthStore();
  auth.setSession({
    accessToken: "access",
    expiresIn: 1_800,
    user,
  });
  auth.setWorkspaceSession({
    user,
    workspaces,
    truncated: false,
  });
  return { auth, user, workspaces };
}
