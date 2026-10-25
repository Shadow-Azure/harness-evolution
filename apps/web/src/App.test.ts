// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import { healthFixtures } from "@harness/contracts";
import App from "./App.vue";
import { createAppRouter } from "./router";
import { useAuthStore } from "./stores/auth";
import { server } from "./test/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      /** @param callback Observed element resize callback. */
      constructor(private readonly callback: ResizeObserverCallback) {}
      /** @returns No value. */
      observe() {
        this.callback([], this as unknown as ResizeObserver);
      }
      /** @returns No value. */
      unobserve() {}
      /** @returns No value. */
      disconnect() {}
    }
  );
});
afterEach(() => server.resetHandlers());
afterEach(() => {
  vi.unstubAllGlobals();
});
afterAll(() => server.close());

async function mountApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { gcTime: 0, retry: false, staleTime: 0 } }
  });
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().setSession({
    accessToken: "test-access",
    expiresIn: 1_800,
    user: {
      id: "u-test",
      username: "operator",
      displayName: "测试用户",
      role: "member",
      mustChangePassword: false,
    },
  });
  const router = createAppRouter();
  const wrapper = mount(App, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient }], pinia, router]
    }
  });
  await router.isReady();
  await flushPromises();
  return { router, wrapper };
}

describe("App shell", () => {
  it("uses /sessions as the default empty view and shows canonical health", async () => {
    server.use(http.get("/api/health", () => HttpResponse.json(healthFixtures.healthy)));
    const { router, wrapper } = await mountApp();

    expect(router.currentRoute.value.path).toBe("/sessions");
    expect(wrapper.find("nav").text()).toContain("Sessions");
    expect(wrapper.text()).toContain("Session 浏览器");
    expect(wrapper.text()).toContain("API 已连接 · SQLite");
  });

  it("keeps the shell mounted when health is unavailable", async () => {
    server.use(
      http.get("/api/health", () => HttpResponse.json(healthFixtures.unavailable, { status: 503 }))
    );
    const { wrapper } = await mountApp();

    expect(wrapper.text()).toContain("数据库异常");
  });

  it("lazily reaches the evolution view", async () => {
    const { router, wrapper } = await mountApp();
    await router.push("/evolution");
    await flushPromises();

    expect(router.currentRoute.value.path).toBe("/evolution");
    expect(wrapper.text()).toContain("Evolution 骨架");
  });
});
