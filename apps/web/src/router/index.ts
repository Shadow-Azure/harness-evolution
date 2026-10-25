import { createRouter, createWebHistory, type RouterOptions } from "vue-router";

import SessionsPage from "../pages/sessions/Index.vue";

/**
 * Create the application router.
 * @returns History router with a synchronous default page and lazy non-default page.
 */
export function createAppRouter() {
  return createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
      { path: "/", redirect: "/sessions" },
      { path: "/sessions", component: SessionsPage },
      {
        component: () => import("../pages/evolution/Index.vue"),
        path: "/evolution"
      }
    ]
  } satisfies RouterOptions);
}
