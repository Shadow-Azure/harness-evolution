// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { server } from "../../test/server";
import { useAuthStore } from "../../stores/auth";
import { createAppRouter } from "../../router";
import TopNav from "./TopNav.vue";
import TopNavSource from "./TopNav.vue?raw";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("top navigation user area", () => {
  it("styles the rendered user popover button", () => {
    expect(TopNavSource).toContain(".user-popover button:hover");
    expect(TopNavSource).not.toContain(".user-area button:hover");
  });

  it("shows the current user and clears session state on logout", async () => {
    server.use(http.post("/api/auth/logout", () => new HttpResponse(null, { status: 204 })));
    const pinia = createPinia();
    setActivePinia(pinia);
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
    const queryClient = new QueryClient();
    queryClient.setQueryData(["sessions"], [{ id: "s-1" }]);
    const router = createAppRouter();
    await router.push("/sessions");
    await router.isReady();
    const wrapper = mount(TopNav, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }], pinia, router],
      },
    });

    expect(wrapper.text()).toContain("操作员");
    expect(wrapper.get("details.user-menu summary").text()).toBe("操作员");
    await wrapper.get("button[data-testid='logout']").trigger("click");
    await flushPromises();

    await vi.waitFor(() => {
      expect(store.user).toBeNull();
      expect(queryClient.getQueryData(["sessions"])).toBeUndefined();
      expect(router.currentRoute.value.path).toBe("/login");
    });
  });

  it("renders all M1 destinations and the optional demo badge", async () => {
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

    const wrapper = mount(TopNav, {
      props: { demo: true },
      global: {
        plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }], pinia, router],
      },
    });

    expect(wrapper.find("nav").text()).toContain("Sessions");
    expect(wrapper.find("nav").text()).toContain("Errors");
    expect(wrapper.find("nav").text()).toContain("Evolution");
    expect(wrapper.get("[data-testid='demo-badge']").text()).toContain("演示数据");
    expect(wrapper.get("nav a.router-link-active").text()).toBe("Errors");
  });
});
