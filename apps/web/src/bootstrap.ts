import { VueQueryPlugin, type QueryClient } from "@tanstack/vue-query";
import type { Pinia } from "pinia";
import type { App } from "vue";
import type { Router } from "vue-router";

import { installAuthRuntime } from "./auth/runtime";
import { useAppConfigStore } from "./stores/appConfig";
import { useAuthStore } from "./stores/auth";

const APP_CONFIG_LOAD_TIMEOUT_MS = 2_000;

/**
 * Bound the pre-mount brand fetch so a stalled endpoint cannot block first paint.
 * The store keeps its own request alive and updates reactive brand state if it
 * resolves after the timeout.
 * @param load Brand loader that already falls back on failure.
 * @returns No value.
 */
async function loadBrandWithinTimeout(load: () => Promise<void>): Promise<void> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const pending = load().catch(() => {
    // The store owns the visible fallback; this boundary must never throw.
  });
  await Promise.race([
    pending,
    new Promise<void>((resolve) => {
      timer = setTimeout(resolve, APP_CONFIG_LOAD_TIMEOUT_MS);
    }),
  ]);
  if (timer !== undefined) {
    clearTimeout(timer);
  }
}

/** Injected dependencies for the deterministic browser bootstrap sequence. */
export type BootstrapAppOptions = {
  app: App;
  loadAppConfig?: () => Promise<void>;
  mountTarget: string;
  pinia: Pinia;
  queryClient: QueryClient;
  restore?: () => Promise<boolean>;
  router: Router;
};

/**
 * Install plugins, restore authentication, await route readiness, and mount.
 * @param options Application composition and test seams.
 * @returns No value.
 */
export async function bootstrapApp(options: BootstrapAppOptions): Promise<void> {
  const { app, mountTarget, pinia, queryClient, router } = options;
  if (typeof history !== "undefined" && "scrollRestoration" in history) {
    history.scrollRestoration = "manual";
  }
  app.use(pinia);
  const appConfig = useAppConfigStore(pinia);
  await loadBrandWithinTimeout(
    options.loadAppConfig ?? (() => appConfig.load()),
  );
  app.use(VueQueryPlugin, { queryClient });
  installAuthRuntime(router, pinia, queryClient);
  app.use(router);

  const auth = useAuthStore(pinia);
  await (options.restore ?? (() => auth.tryRefresh()))();
  await router.isReady();
  app.mount(mountTarget);
}
