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
import { signInWithWorkspace, TEST_WORKSPACE_ID } from "./test/auth";
import { server } from "./test/server";

const ws = `/workspaces/${TEST_WORKSPACE_ID}`;

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  server.use(
    http.get(`/api/workspaces/${TEST_WORKSPACE_ID}/sessions`, () =>
      HttpResponse.json({ items: [] }),
    ),
    http.get("/api/acquisition/status", () =>
      HttpResponse.json({
        status: "idle",
        pending: 0,
        processed: 0,
        imported: 0,
        skipped: 0,
        errors: [],
        badCaseSync: null,
        badCaseCatalogSync: null,
        badCaseAnalysis: null,
      }),
    ),
  );
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
  signInWithWorkspace({
    id: "u-test",
    username: "operator",
    displayName: "测试用户",
    role: "member",
    mustChangePassword: false,
  });
  window.history.replaceState({}, "", `${ws}/sessions`);
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
  it("renders the shared loading state until canonical health settles", async () => {
    server.use(http.get("/api/health", async () => await new Promise<Response>(() => {})));

    const { wrapper } = await mountApp();

    expect(wrapper.find("[data-testid='health-loading']").exists()).toBe(true);
    expect(wrapper.get("[role='status']").attributes("aria-label")).toBe(
      "正在连接 API",
    );
    expect(wrapper.find("nav").exists()).toBe(true);
  });

  it("uses the workspace session view without developer status chrome", async () => {
    server.use(http.get("/api/health", () => HttpResponse.json(healthFixtures.healthy)));
    const { router, wrapper } = await mountApp();

    expect(router.currentRoute.value.path).toBe(`${ws}/sessions`);
    expect(wrapper.find("nav").text()).toContain("Session 错误查看");
    expect(wrapper.find("nav").text()).toContain("自进化");
    expect(wrapper.find("nav").text()).not.toContain("Errors");
    expect(wrapper.text()).toContain("Session 浏览器");
    expect(wrapper.text()).not.toContain("API 已连接");
    expect(wrapper.find("[data-testid='demo-badge']").exists()).toBe(false);
  });

  it("keeps the shell mounted when health is unavailable", async () => {
    let attempts = 0;
    server.use(
      http.get("/api/health", () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json(healthFixtures.unavailable, { status: 503 })
          : HttpResponse.json(healthFixtures.healthy);
      }),
    );
    const { wrapper } = await mountApp();

    expect(wrapper.find("nav").exists()).toBe(true);
    expect(wrapper.get("[role='alert']").text()).toContain("API 或数据库当前不可用");
    expect(wrapper.text()).not.toContain("Session 浏览器");

    await wrapper.get("[role='alert'] button").trigger("click");
    await flushPromises();

    expect(wrapper.find("[role='alert']").exists()).toBe(false);
    expect(wrapper.text()).toContain("Session 浏览器");
    expect(attempts).toBe(2);
  });

  it("turns a standard error-envelope health response into the retryable shell state", async () => {
    let attempts = 0;
    server.use(
      http.get("/api/health", () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json(
              {
                error: {
                  code: "HEALTH_UNAVAILABLE",
                  message: "database unavailable",
                },
              },
              { status: 503 },
            )
          : HttpResponse.json(healthFixtures.healthy);
      }),
    );
    const { wrapper } = await mountApp();

    expect(wrapper.find("nav").exists()).toBe(true);
    expect(wrapper.get("[role='alert']").text()).toContain("HEALTH_UNAVAILABLE");
    expect(wrapper.text()).not.toContain("Session 浏览器");

    await wrapper.get("[role='alert'] button").trigger("click");
    await flushPromises();

    expect(wrapper.find("[role='alert']").exists()).toBe(false);
    expect(wrapper.text()).toContain("Session 浏览器");
    expect(attempts).toBe(2);
  });

  it("lazily reaches the evolution view", async () => {
    const { router, wrapper } = await mountApp();
    await router.push(`${ws}/evolution`);
    await flushPromises();

    expect(router.currentRoute.value.path).toBe(`${ws}/evolution`);
    expect(wrapper.text()).toContain("自进化");
  });

  it("shows the demo badge only for the demo phase", async () => {
    server.use(
      http.get("/api/health", () =>
        HttpResponse.json({ ...healthFixtures.healthy, phase: "demo" }),
      ),
    );

    const { wrapper } = await mountApp();

    expect(wrapper.get("[data-testid='demo-badge']").text()).toContain("演示数据");
  });

  it("hides the demo badge for live data", async () => {
    server.use(
      http.get("/api/health", () =>
        HttpResponse.json({ ...healthFixtures.healthy, phase: "live" }),
      ),
    );

    const { wrapper } = await mountApp();

    expect(wrapper.find("[data-testid='demo-badge']").exists()).toBe(false);
  });

  it("retires the top-level errors route into the sessions view", async () => {
    const { router, wrapper } = await mountApp();

    await router.push("/errors");
    await flushPromises();

    expect(router.currentRoute.value.path).toBe(`${ws}/sessions`);
    expect(wrapper.text()).not.toContain("请选择会话");
  });
});
