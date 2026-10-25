import type { Router } from "vue-router";
import type { Pinia } from "pinia";

import {
  setAccessTokenProvider,
  setAuthExpiredHandler,
  setPasswordChangeHandler,
  setRefreshHandler,
} from "../api/http";
import { safeRedirect } from "../router/safeRedirect";
import { useAuthStore } from "../stores/auth";

/**
 * Connect transport callbacks to the auth store and router.
 * @param router Application router receiving recovery navigation.
 * @param pinia Application Pinia instance, or the active test instance.
 * @returns No value.
 */
export function installAuthRuntime(router: Router, pinia?: Pinia): void {
  const auth = useAuthStore(pinia);
  setAccessTokenProvider(() => auth.accessToken);
  setRefreshHandler(() => auth.refresh());
  setAuthExpiredHandler((redirect) => {
    auth.clear();
    void router.push({
      path: "/login",
      query: { redirect: safeRedirect(redirect) },
    });
  });
  setPasswordChangeHandler((redirect) => {
    auth.markPasswordChangeRequired();
    void router.push({
      path: "/change-password",
      query: { redirect: safeRedirect(redirect) },
    });
  });
}
