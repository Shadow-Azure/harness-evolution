import { createRouter, createWebHistory, type RouterOptions } from "vue-router";

import SessionsPage from "../pages/sessions/Index.vue";
import { useAuthStore } from "../stores/auth";
import { safeRedirect } from "./safeRedirect";

/**
 * Create the authenticated application router.
 * @returns History router with public login routes and protected application routes.
 */
export function createAppRouter() {
  const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
      { path: "/", redirect: "/sessions" },
      {
        path: "/login",
        component: () => import("../pages/login/Index.vue"),
        meta: { authLayout: true, public: true },
      },
      {
        path: "/change-password",
        component: () => import("../pages/login/ChangePassword.vue"),
        meta: { authLayout: true },
      },
      {
        path: "/sessions",
        component: SessionsPage,
        meta: { workspace: true },
      },
      {
        path: "/sessions/:sessionId",
        component: SessionsPage,
        meta: { workspace: true },
      },
      {
        component: () => import("../pages/evolution/Index.vue"),
        path: "/evolution",
      },
      {
        component: () => import("../pages/errors/Index.vue"),
        path: "/errors",
      },
      {
        component: () => import("../pages/NotFound.vue"),
        path: "/:pathMatch(.*)*",
      },
    ],
  } satisfies RouterOptions);

  router.beforeEach(async (to) => {
    const auth = useAuthStore();
    if (!auth.isBootstrapped) {
      await auth.tryRefresh();
    }
    if (!auth.isAuthenticated && to.path !== "/login") {
      return { path: "/login", query: { redirect: to.fullPath } };
    }
    if (auth.isAuthenticated && to.path === "/login") {
      return safeRedirect(to.query.redirect, "/sessions");
    }
    if (
      auth.user?.mustChangePassword &&
      to.path !== "/change-password" &&
      to.path !== "/login"
    ) {
      return { path: "/change-password", query: { redirect: to.fullPath } };
    }
    return true;
  });

  return router;
}
