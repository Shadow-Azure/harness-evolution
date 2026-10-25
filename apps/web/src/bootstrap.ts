import { VueQueryPlugin, type QueryClient } from "@tanstack/vue-query";
import type { Pinia } from "pinia";
import type { App } from "vue";
import type { Router } from "vue-router";

import { installAuthRuntime } from "./auth/runtime";
import { useAuthStore } from "./stores/auth";

/** Injected dependencies for the deterministic browser bootstrap sequence. */
export type BootstrapAppOptions = {
  app: App;
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
  app.use(pinia);
  app.use(VueQueryPlugin, { queryClient });
  installAuthRuntime(router, pinia);
  app.use(router);

  const auth = useAuthStore(pinia);
  await (options.restore ?? (() => auth.tryRefresh()))();
  await router.isReady();
  app.mount(mountTarget);
}
