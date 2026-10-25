// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createAppRouter } from "../router";
import ErrorsPage from "./errors/Index.vue";
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

  it("explains that the top-level errors entry arrives later", async () => {
    const wrapper = await withRouter(ErrorsPage);

    expect(wrapper.text()).toContain("暂无问题");
    expect(wrapper.text()).toContain("问题归属将在后续 milestone 接入");
  });

  it("keeps the evolution canvas while using the shared empty presentation", async () => {
    const wrapper = await withRouter(EvolutionPage);

    expect(wrapper.text()).toContain("暂无自进化运行");
    expect(wrapper.find(".canvas").exists()).toBe(true);
  });

  it("presents a terminal not-found state with the canonical copy", async () => {
    const wrapper = await withRouter(NotFound);

    expect(wrapper.text()).toContain("404");
    expect(wrapper.text()).toContain("页面不存在或已删除");
    expect(wrapper.find("button").exists()).toBe(false);
  });
});
