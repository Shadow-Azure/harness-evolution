// @vitest-environment jsdom

import type { SessionWorkspace } from "@harness/contracts";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SessionsPage from "./pages/sessions/Index.vue";
import { createAppRouter } from "./router";
import { useAuthStore } from "./stores/auth";
import { testWorkspace, TEST_WORKSPACE_ID } from "./test/auth";
import { LAST_WORKSPACE_KEY } from "./router/workspace";

const ws = `/workspaces/${TEST_WORKSPACE_ID}`;

function signIn(
  workspaces: SessionWorkspace[] = [testWorkspace()],
  mustChangePassword = false,
) {
  const store = useAuthStore();
  const user = {
    id: "u-1",
    username: "operator",
    displayName: "操作员",
    role: "member" as const,
    mustChangePassword,
  };
  store.setSession({
    accessToken: "access",
    expiresIn: 1_800,
    user,
  });
  store.setWorkspaceSession({ user, workspaces, truncated: false });
  return store;
}

const storage = new Map<string, string>();

beforeEach(() => {
  setActivePinia(createPinia());
  storage.clear();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
    clear: () => storage.clear(),
  });
  window.history.replaceState({}, "", "/");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("web router", () => {
  it("mounts the synchronous session list inside the workspace shell", () => {
    const router = createAppRouter();
    const shell = router.options.routes.find(
      (route) => route.path === "/workspaces/:wid",
    );
    const sessions = shell?.children?.find(
      (route) => route.path === "sessions",
    );

    expect(shell?.meta?.workspace).toBe(true);
    expect(sessions?.component).toBe(SessionsPage);
  });

  it("lazily loads evolution and error pages under the workspace shell", async () => {
    const router = createAppRouter();
    const shell = router.options.routes.find(
      (route) => route.path === "/workspaces/:wid",
    );
    const children = shell?.children ?? [];
    const evolution = children.find(
      (route) => route.path === "evolution",
    );
    const errors = children.find(
      (route) => route.path === "sessions/:sessionId/errors",
    );
    const targets = children.find(
      (route) => route.path === "evolution/targets",
    );
    const admin = children.find((route) => route.path === "admin");

    expect(typeof evolution?.component).toBe("function");
    const evolutionComponent = await (
      evolution?.component as () => Promise<{ default: { name: string } }>
    )();
    expect(evolutionComponent.default.name).toBe("EvolutionPage");

    expect(typeof errors?.component).toBe("function");
    const errorsComponent = await (
      errors?.component as () => Promise<{ default: { name: string } }>
    )();
    expect(errorsComponent.default.name).toBe("ErrorsPage");

    expect(typeof targets?.component).toBe("function");
    const targetsComponent = await (
      targets?.component as () => Promise<{ default: { name: string } }>
    )();
    expect(targetsComponent.default.name).toBe("TargetConfigPage");

    expect(typeof admin?.component).toBe("function");
    const adminComponent = await (
      admin?.component as () => Promise<{ default: { name: string } }>
    )();
    expect(adminComponent.default.name).toBe("WorkspaceAdminPage");
  });

  it("keeps the development-only Agent tree visual fixture", async () => {
    const router = createAppRouter();
    const route = router.options.routes.find(
      (item) => item.path === "/agent-tree-demo",
    );

    expect(import.meta.env.DEV).toBe(true);
    expect(route?.meta?.workspace).toBe(true);
    expect(typeof route?.component).toBe("function");
    const component = await (
      route?.component as () => Promise<{ default: { name: string } }>
    )();
    expect(component.default.name).toBe("AgentTreeDemoPage");
  });

  it("redirects unauthenticated workspace routes to login with the original path", async () => {
    const router = createAppRouter();
    await router.push(`${ws}/sessions/s-1?q=error`);
    await router.isReady();

    expect(router.currentRoute.value.path).toBe("/login");
    expect(router.currentRoute.value.query.redirect).toBe(
      `${ws}/sessions/s-1?q=error`,
    );
  });

  it("redirects unauthenticated legacy routes to login", async () => {
    const router = createAppRouter();
    await router.push("/evolution/targets");
    await router.isReady();

    expect(router.currentRoute.value.path).toBe("/login");
    expect(router.currentRoute.value.query.redirect).toBe(
      "/evolution/targets",
    );
  });

  it("lets a visible workspace route resolve and remembers it", async () => {
    signIn();
    const router = createAppRouter();
    await router.push(`${ws}/sessions`);
    await router.isReady();

    expect(router.currentRoute.value.fullPath).toBe(`${ws}/sessions`);
    expect(window.localStorage.getItem(LAST_WORKSPACE_KEY)).toBe(
      TEST_WORKSPACE_ID,
    );
  });

  it("sends an invisible workspace to the chooser without leaking data", async () => {
    signIn();
    const router = createAppRouter();
    await router.push("/workspaces/someone-else/sessions");
    await router.isReady();

    expect(router.currentRoute.value.path).toBe("/workspaces");
    expect(router.currentRoute.value.query.reason).toBe("forbidden");
  });

  it("redirects a legacy deep link once and keeps its query", async () => {
    signIn();
    const router = createAppRouter();
    await router.push("/sessions/s-1?q=error&status=problem");
    await router.isReady();

    expect(router.currentRoute.value.fullPath).toBe(
      `${ws}/sessions/s-1?q=error&status=problem`,
    );
    expect(window.history.state.replaced).toBe(true);
  });

  it("prefers the remembered workspace while it is still visible", async () => {
    window.localStorage.setItem(LAST_WORKSPACE_KEY, "ws-remembered");
    signIn([
      testWorkspace({ id: "ws-remembered", name: "记忆空间" }),
      testWorkspace({ id: "ws-other", name: "其他空间" }),
    ]);
    const router = createAppRouter();
    await router.push("/evolution");
    await router.isReady();

    expect(router.currentRoute.value.path).toBe(
      "/workspaces/ws-remembered/evolution",
    );
  });

  it("falls back to the single visible workspace instead of guessing", async () => {
    signIn([testWorkspace({ id: "ws-only", name: "唯一空间" })]);
    const router = createAppRouter();
    await router.push("/sessions");
    await router.isReady();

    expect(router.currentRoute.value.path).toBe(
      "/workspaces/ws-only/sessions",
    );
  });

  it("asks for a choice when multiple workspaces are unrelated to the link", async () => {
    signIn([
      testWorkspace({ id: "ws-a", name: "空间 A" }),
      testWorkspace({ id: "ws-b", name: "空间 B" }),
    ]);
    const router = createAppRouter();
    await router.push("/sessions?q=agent");
    await router.isReady();

    expect(router.currentRoute.value.path).toBe("/workspaces");
    expect(router.currentRoute.value.query.reason).toBe("select");
  });

  it("routes the root through the remembered workspace", async () => {
    window.localStorage.setItem(LAST_WORKSPACE_KEY, TEST_WORKSPACE_ID);
    signIn();
    const router = createAppRouter();
    await router.push("/");
    await router.isReady();

    expect(router.currentRoute.value.path).toBe(`${ws}/sessions`);
  });

  it("keeps login public and sends authenticated users to a safe redirect", async () => {
    signIn();
    const router = createAppRouter();
    await router.push("/login?redirect=/evolution");
    await router.isReady();

    expect(router.currentRoute.value.fullPath).toBe(`${ws}/evolution`);
  });

  it("rejects an external redirect target", async () => {
    signIn();
    const router = createAppRouter();
    await router.push("/login?redirect=//evil.example");
    await router.isReady();

    expect(router.currentRoute.value.fullPath).toBe(`${ws}/sessions`);
  });

  it("forces a first-login password change while preserving the destination", async () => {
    signIn([testWorkspace()], true);
    const router = createAppRouter();
    await router.push("/sessions?sort=recent");
    await router.isReady();

    expect(router.currentRoute.value.path).toBe("/change-password");
    expect(router.currentRoute.value.query.redirect).toBe(
      "/sessions?sort=recent",
    );
  });
});
