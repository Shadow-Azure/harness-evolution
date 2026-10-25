// @vitest-environment jsdom

import { describe, expect, it } from "vitest";

import SessionsPage from "./pages/sessions/Index.vue";
import { createAppRouter } from "./router";

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
});
