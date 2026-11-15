import { createRouter, createWebHistory, type RouterOptions } from "vue-router";

import SessionsPage from "../pages/sessions/Index.vue";
import { useAuthStore } from "../stores/auth";
import { safeRedirect } from "./safeRedirect";
import {
  defaultLandingPath,
  isLegacyWorkspacePath,
  legacyWorkspaceTarget,
  readLastWorkspaceId,
  rememberWorkspace,
  resolveLegacyWorkspace,
  workspacePath,
} from "./workspace";

/**
 * Create the authenticated application router.
 * @returns History router with public login routes and the workspace shell.
 */
export function createAppRouter() {
  const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
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
        path: "/workspaces",
        component: () => import("../pages/workspaces/Chooser.vue"),
        meta: { chooser: true },
      },
      {
        path: "/workspaces/:wid",
        component: () => import("../pages/workspaces/Shell.vue"),
        meta: { workspace: true },
        children: [
          {
            path: "",
            name: "workspace-root",
            redirect: (to) => workspacePath(String(to.params.wid), "sessions"),
          },
          {
            path: "sessions",
            name: "workspace-sessions",
            component: SessionsPage,
          },
          {
            path: "sessions/:sessionId",
            name: "workspace-session",
            component: SessionsPage,
          },
          {
            path: "sessions/:sessionId/errors",
            name: "workspace-errors",
            component: () => import("../pages/errors/Index.vue"),
          },
          {
            path: "evolution",
            name: "workspace-evolution",
            component: () => import("../pages/evolution/Index.vue"),
          },
          {
            path: "evolution/runs/:runId",
            name: "workspace-evolution-run",
            component: () => import("../pages/evolution/RunDetail.vue"),
          },
          {
            path: "evolution/cluster/:runId",
            name: "workspace-evolution-cluster",
            component: () => import("../pages/evolution/ClusterPreview.vue"),
          },
          {
            path: "evolution/targets",
            name: "workspace-evolution-targets",
            component: () => import("../pages/evolution/targets/Index.vue"),
          },
          {
            path: "admin",
            name: "workspace-admin",
            component: () => import("../pages/workspaces/Admin.vue"),
          },
        ],
      },
      ...(import.meta.env.DEV
        ? [
            {
              path: "/agent-tree-demo",
              component: () => import("../pages/agent-tree-demo/Index.vue"),
              meta: { workspace: true },
            },
          ]
        : []),
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

    const isAuthSurface =
      to.path === "/login" || to.path === "/change-password";

    if (!auth.isAuthenticated && !isAuthSurface) {
      return { path: "/login", query: { redirect: to.fullPath } };
    }
    if (auth.isAuthenticated && to.path === "/login") {
      return safeRedirect(to.query.redirect, defaultLandingPath(auth));
    }
    if (auth.user?.mustChangePassword && !isAuthSurface) {
      return { path: "/change-password", query: { redirect: to.fullPath } };
    }
    if (!auth.isAuthenticated) {
      return true;
    }

    if (isLegacyWorkspacePath(to.path)) {
      const workspaceId = resolveLegacyWorkspace(
        readLastWorkspaceId(),
        auth.workspaces,
      );
      if (!workspaceId) {
        return {
          path: "/workspaces",
          query: { reason: "select" },
          replace: true,
        };
      }
      return {
        path: legacyWorkspaceTarget(workspaceId, to.path),
        query: to.query,
        hash: to.hash,
        replace: true,
      };
    }

    const workspaceId = to.params.wid;
    if (typeof workspaceId === "string" && workspaceId.length > 0) {
      if (!auth.workspaceById(workspaceId)) {
        return {
          path: "/workspaces",
          query: { reason: "forbidden" },
          replace: true,
        };
      }
      rememberWorkspace(workspaceId);
    }
    return true;
  });

  return router;
}
