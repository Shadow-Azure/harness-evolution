// @vitest-environment jsdom

import { QueryClient } from "@tanstack/vue-query";
import { createPinia } from "pinia";
import { describe, expect, it, vi } from "vitest";

import { bootstrapApp, type BootstrapAppOptions } from "./bootstrap";

describe("application bootstrap", () => {
  it("restores auth and waits for the router before mounting", async () => {
    Object.defineProperty(history, "scrollRestoration", {
      configurable: true,
      value: "auto",
      writable: true,
    });
    const calls: string[] = [];
    const pinia = createPinia();
    const queryClient = new QueryClient();
    const router = {
      install: vi.fn(),
      isReady: vi.fn(async () => {
        calls.push("router.isReady");
      }),
      push: vi.fn(),
      currentRoute: { value: { fullPath: "/sessions" } },
    };
    const app = {
      use: vi.fn(() => {
        calls.push("app.use");
        return app;
      }),
      mount: vi.fn(() => {
        calls.push("mount");
      }),
    };
    const restore = vi.fn(async () => {
      calls.push("tryRefresh");
      return true;
    });
    const options = {
      app,
      pinia,
      queryClient,
      router,
      mountTarget: "#app",
      restore,
    } as unknown as BootstrapAppOptions;

    await bootstrapApp(options);

    expect(calls.slice(-3)).toEqual(["tryRefresh", "router.isReady", "mount"]);
    expect(app.use).toHaveBeenCalledTimes(3);
    expect(app.mount).toHaveBeenCalledWith("#app");
    expect(history.scrollRestoration).toBe("manual");
  });
});
