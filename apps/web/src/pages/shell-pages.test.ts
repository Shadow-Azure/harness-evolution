// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { http, HttpResponse } from "msw";
import { createPinia, setActivePinia } from "pinia";
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

import { createAppRouter } from "../router";
import { server } from "../test/server";
import { useAuthStore } from "../stores/auth";
import EvolutionPage from "./evolution/Index.vue";
import NotFound from "./NotFound.vue";
import SessionsPage from "./sessions/Index.vue";

beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      /** @param callback Observed resize callback. */
      constructor(private readonly callback: ResizeObserverCallback) {}
      /** @returns No value. */
      observe() {
        this.callback([], this as unknown as ResizeObserver);
      }
      /** @returns No value. */
      unobserve() {}
      /** @returns No value. */
      disconnect() {}
    },
  );
});

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

async function withRouter(component: Parameters<typeof mount>[0]) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createAppRouter();
  await router.push("/sessions");
  await router.isReady();
  return mount(component, {
    global: {
      plugins: [
        [VueQueryPlugin, { queryClient: new QueryClient() }],
        pinia,
        router,
      ],
    },
  });
}

describe("M1 shell pages", () => {
  it("uses the common empty state without fabricating sessions", async () => {
    const wrapper = await withRouter(SessionsPage);

    expect(wrapper.text()).toContain("Session 浏览器");
    expect(wrapper.find("[data-testid='session-card']").exists()).toBe(false);
  });

  it("retires the top-level errors entry into the sessions view", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore().setSession({
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
    await router.push("/errors");
    await router.isReady();

    expect(router.currentRoute.value.path).toBe("/sessions");
  });

  it("renders the backend-owned evolution run list shell", async () => {
    server.use(
      http.get("/api/evolution/runs", () =>
        HttpResponse.json({ running: [], history: [] })),
    );
    const wrapper = await withRouter(EvolutionPage);
    await flushPromises();

    expect(wrapper.find("[data-testid='evolution-run-list']").exists()).toBe(true);
    expect(wrapper.text()).toContain("当前没有正在执行的自进化");
    expect(wrapper.find(".canvas").exists()).toBe(false);
  });

  it("presents a terminal not-found state with the canonical copy", async () => {
    const wrapper = await withRouter(NotFound);

    expect(wrapper.text()).toContain("404");
    expect(wrapper.text()).toContain("页面不存在或已删除");
    expect(wrapper.find("button").exists()).toBe(false);
  });
});
