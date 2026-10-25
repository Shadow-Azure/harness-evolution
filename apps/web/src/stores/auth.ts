import type {
  ChangePasswordRequest,
  LoginRequest,
  LoginResponse,
  PublicUser,
} from "@harness/contracts";
import { defineStore } from "pinia";
import { computed, ref } from "vue";

import {
  changePassword as changePasswordRequest,
  login as loginRequest,
  logout as logoutRequest,
  me,
  refresh as refreshRequest,
} from "../api/auth";

type SessionInput = Pick<LoginResponse, "accessToken" | "expiresIn" | "user">;

/** In-memory authentication state; refresh credentials stay in the httpOnly cookie. */
export const useAuthStore = defineStore("auth", () => {
  const accessToken = ref<string | null>(null);
  const user = ref<PublicUser | null>(null);
  const isBootstrapped = ref(false);
  const isAuthenticated = computed(() => Boolean(accessToken.value && user.value));
  let bootstrapPromise: Promise<boolean> | null = null;

  /**
   * Install a successful login payload into memory.
   * @param session Authenticated token and public user.
   * @returns No value.
   */
  function setSession(session: SessionInput): void {
    accessToken.value = session.accessToken;
    user.value = session.user;
    isBootstrapped.value = true;
  }

  /**
   * Clear all in-memory authentication state.
   * @returns No value.
   */
  function clear(): void {
    accessToken.value = null;
    user.value = null;
  }

  /**
   * Authenticate with username and password.
   * @param credentials Login form credentials.
   * @returns The authenticated public user.
   */
  async function login(credentials: LoginRequest): Promise<PublicUser> {
    const response = await loginRequest(credentials);
    setSession(response);
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
      user.value = await me();
      isBootstrapped.value = true;
      return true;
    } catch {
      clear();
      isBootstrapped.value = true;
      return false;
    }
  }

  /**
   * Load the current user and replace stale public fields.
   * @returns The latest public user.
   */
  async function loadCurrentUser(): Promise<PublicUser> {
    const current = await me();
    user.value = current;
    return current;
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
    isBootstrapped,
    isAuthenticated,
    setSession,
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
