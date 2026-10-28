// @vitest-environment jsdom

import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";

import SessionsPage from "./pages/sessions/Index.vue";
import { createAppRouter } from "./router";
import { useAuthStore } from "./stores/auth";

beforeEach(() => {
  setActivePinia(createPinia());
});

describe("web router", () => {
  it("redirects the root to the synchronous sessions shell", () => {
    const router = createAppRouter();
    const rootRoute = router.options.routes.find((route) => route.path === "/");

    expect(rootRoute?.redirect).toBe("/sessions");
    expect(
      router.options.routes.find((route) => route.path === "/sessions")?.component
    ).toBe(SessionsPage);
  });

  it("lazily loads the evolution page", async () => {
    const router = createAppRouter();
    const evolutionRoute = router.options.routes.find((route) => route.path === "/evolution");
    const loader = evolutionRoute?.component;

    expect(typeof loader).toBe("function");
    const component = await (loader as () => Promise<{ default: { name: string } }>)();
    expect(component.default.name).toBe("EvolutionPage");
  });

  it("protects and lazily loads the evolution target configuration page", async () => {
    const router = createAppRouter();
    const route = router.options.routes.find(
      (item) => item.path === "/evolution/targets",
    );

    expect(route?.meta?.public).not.toBe(true);
    expect(typeof route?.component).toBe("function");
    const component = await (
      route?.component as () => Promise<{ default: { name: string } }>
    )();
    expect(component.default.name).toBe("TargetConfigPage");
  });

  it("lazily loads the development-only Agent tree visual fixture", async () => {
    const router = createAppRouter();
    const route = router.options.routes.find((item) => item.path === "/agent-tree-demo");
    const loader = route?.component;

    expect(import.meta.env.DEV).toBe(true);
    expect(route?.meta?.workspace).toBe(true);
    expect(typeof loader).toBe("function");
    const component = await (loader as () => Promise<{ default: { name: string } }>)();
    expect(component.default.name).toBe("AgentTreeDemoPage");
  });

  it("retires the top-level errors route with a redirect to sessions", () => {
    const router = createAppRouter();
    const errorsRoute = router.options.routes.find((route) => route.path === "/errors");

    expect(errorsRoute?.redirect).toBe("/sessions");
    expect(errorsRoute?.component).toBeUndefined();
  });

  it("protects and lazily loads the Session error-detail route", async () => {
    const router = createAppRouter();
    const route = router.options.routes.find(
      (item) => item.path === "/sessions/:sessionId/errors",
    );

    expect(route?.meta?.public).not.toBe(true);
    expect(typeof route?.component).toBe("function");
    const component = await (
      route?.component as () => Promise<{ default: { name: string } }>
    )();
    expect(component.default.name).toBe("ErrorsPage");
  });

  it("redirects unauthenticated protected routes to login with the original path", async () => {
    const router = createAppRouter();
    await router.push("/sessions/s-1?q=error");
    await router.isReady();

    expect(router.currentRoute.value.path).toBe("/login");
    expect(router.currentRoute.value.query.redirect).toBe("/sessions/s-1?q=error");
  });

  it("redirects unauthenticated target configuration to login", async () => {
    const router = createAppRouter();
    await router.push("/evolution/targets");
    await router.isReady();

    expect(router.currentRoute.value.path).toBe("/login");
    expect(router.currentRoute.value.query.redirect).toBe("/evolution/targets");
  });

  it("keeps login public and sends authenticated users to a safe redirect", async () => {
    const store = useAuthStore();
    store.setSession({
      accessToken: "access",
      expiresIn: 1_800,
      user: {
        id: "u-1",
        username: "operator",
        displayName: "操作员",
        role: "member",
        mustChangePassword: false,
      },
    });
    const router = createAppRouter();
    await router.push("/login?redirect=/evolution");
    await router.isReady();

    expect(router.currentRoute.value.fullPath).toBe("/evolution");
  });

  it("forces a first-login password change while preserving the destination", async () => {
    const store = useAuthStore();
    store.setSession({
      accessToken: "access",
      expiresIn: 1_800,
      user: {
        id: "u-1",
        username: "operator",
        displayName: "操作员",
        role: "member",
        mustChangePassword: true,
      },
    });
    const router = createAppRouter();
    await router.push("/sessions?sort=recent");
    await router.isReady();

    expect(router.currentRoute.value.path).toBe("/change-password");
    expect(router.currentRoute.value.query.redirect).toBe("/sessions?sort=recent");
  });
});
