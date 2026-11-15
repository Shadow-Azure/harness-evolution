import type {
  ChangePasswordRequest,
  LoginRequest,
  LoginResponse,
  PublicUser,
  SessionPayload,
  SessionWorkspace,
} from "@harness/contracts";
import { defineStore } from "pinia";
import { computed, ref } from "vue";

import {
  changePassword as changePasswordRequest,
  getSession,
  login as loginRequest,
  logout as logoutRequest,
  refresh as refreshRequest,
} from "../api/auth";

type SessionInput = Pick<LoginResponse, "accessToken" | "expiresIn" | "user">;

/** In-memory authentication state; refresh credentials stay in the httpOnly cookie. */
export const useAuthStore = defineStore("auth", () => {
  const accessToken = ref<string | null>(null);
  const user = ref<PublicUser | null>(null);
  const workspaces = ref<SessionWorkspace[]>([]);
  const sessionTruncated = ref(false);
  const isBootstrapped = ref(false);
  const isAuthenticated = computed(() => Boolean(accessToken.value && user.value));
  let bootstrapPromise: Promise<boolean> | null = null;

  /**
   * Install a successful login payload into memory.
   *
   * The login response carries identity only; the guard calls `loadSession`
   * before choosing a workspace destination.
   * @param session Authenticated token and public user.
   * @returns No value.
   */
  function setSession(session: SessionInput): void {
    accessToken.value = session.accessToken;
    user.value = session.user;
    isBootstrapped.value = true;
  }

  /**
   * Install the authoritative auth/session payload.
   * @param payload Current user plus every visible workspace.
   * @returns No value.
   */
  function setWorkspaceSession(payload: SessionPayload): void {
    user.value = payload.user;
    workspaces.value = payload.workspaces;
    sessionTruncated.value = payload.truncated;
    isBootstrapped.value = true;
  }

  /**
   * Clear all in-memory authentication state.
   * @returns No value.
   */
  function clear(): void {
    accessToken.value = null;
    user.value = null;
    workspaces.value = [];
    sessionTruncated.value = false;
  }

  /**
   * Look up one visible workspace by route id.
   * @param workspaceId Candidate route workspace identifier.
   * @returns The matching session workspace, or null when invisible.
   */
  function workspaceById(workspaceId: string): SessionWorkspace | null {
    return workspaces.value.find((workspace) => workspace.id === workspaceId) ?? null;
  }

  /**
   * Read the current user, visible workspaces, and truncation flag from the server.
   * @returns The refreshed session payload.
   */
  async function loadSession(): Promise<SessionPayload> {
    const payload = await getSession();
    setWorkspaceSession(payload);
    return payload;
  }

  /**
   * Authenticate with username and password.
   * @param credentials Login form credentials.
   * @returns The authenticated public user.
   */
  async function login(credentials: LoginRequest): Promise<PublicUser> {
    const response = await loginRequest(credentials);
    setSession(response);
    try {
      await loadSession();
    } catch (error) {
      // A failed canonical session read must not leave a half-authenticated
      // store that bounces the login page to an empty chooser.
      clear();
      isBootstrapped.value = true;
      throw error;
    }
    return response.user;
  }

  /**
   * Rotate the refresh token and update the access token.
   * @returns Whether refresh succeeded.
   */
  async function refresh(): Promise<boolean> {
    try {
      const response = await refreshRequest();
      accessToken.value = response.accessToken;
      return true;
    } catch {
      clear();
      return false;
    }
  }

  /**
   * Restore a session from the refresh cookie during application startup.
   * @returns Whether a complete session was restored.
   */
  async function tryRefresh(): Promise<boolean> {
    if (isBootstrapped.value) {
      return isAuthenticated.value;
    }
    if (bootstrapPromise) {
      return bootstrapPromise;
    }
    bootstrapPromise = restoreSession();
    try {
      return await bootstrapPromise;
    } finally {
      bootstrapPromise = null;
    }
  }

  async function restoreSession(): Promise<boolean> {
    const refreshed = await refresh();
    if (!refreshed) {
      isBootstrapped.value = true;
      return false;
    }
    try {
      await loadSession();
      return true;
    } catch {
      clear();
      isBootstrapped.value = true;
      return false;
    }
  }

  /**
   * Reload the current session payload and replace stale public fields.
   * @returns The latest public user.
   */
  async function loadCurrentUser(): Promise<PublicUser> {
    const payload = await loadSession();
    return payload.user;
  }

  /**
   * Complete a forced password change and refresh all derived auth state.
   * @param passwords Current and replacement password values.
   * @returns No value.
   */
  async function changePassword(passwords: ChangePasswordRequest): Promise<void> {
    await changePasswordRequest(passwords);
    if (!(await refresh())) {
      throw new Error("Session expired after changing the password");
    }
    await loadCurrentUser();
  }

  /**
   * Revoke the browser session and clear client caches.
   * @param cache Query cache adapter used to remove server state.
   * @returns No value.
   */
  async function logout(cache: { clear: () => void }): Promise<void> {
    try {
      await logoutRequest();
    } catch {
      // Server-side logout is best effort; local credentials must still disappear.
    } finally {
      clear();
      cache.clear();
    }
  }

  /**
   * Mirror a stale backend forced-change response into local state.
   * @returns No value.
   */
  function markPasswordChangeRequired(): void {
    if (user.value) {
      user.value = { ...user.value, mustChangePassword: true };
    }
  }

  return {
    accessToken,
    user,
    workspaces,
    sessionTruncated,
    isBootstrapped,
    isAuthenticated,
    setSession,
    setWorkspaceSession,
    workspaceById,
    loadSession,
    clear,
    login,
    refresh,
    tryRefresh,
    loadCurrentUser,
    changePassword,
    logout,
    markPasswordChangeRequired,
  };
});
