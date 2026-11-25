// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { createAppRouter } from "../../router";
import { useAppConfigStore } from "../../stores/appConfig";
import { useAuthStore } from "../../stores/auth";
import { server } from "../../test/server";
import { elementPlusComponents } from "../../test/setup";
import { testWorkspace } from "../../test/auth";

const ws = "/workspaces/ws-test";
import ChangePasswordCard from "./ChangePasswordCard.vue";

const firstLoginUser = {
  id: "u-1",
  username: "operator",
  displayName: "操作员",
  role: "member" as const,
  mustChangePassword: true,
};

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

async function mountCard(brand?: { name: string; subtitle: string }) {
  const pinia = createPinia();
  setActivePinia(pinia);
  if (brand) {
    useAppConfigStore().brand = brand;
  }
  const store = useAuthStore();
  store.setSession({
    accessToken: "access",
    expiresIn: 1_800,
    user: firstLoginUser,
  });
  store.setWorkspaceSession({
    user: firstLoginUser,
    workspaces: [testWorkspace({ role: "viewer" })],
    truncated: false,
  });
  const router = createAppRouter();
  await router.push("/change-password?redirect=/sessions");
  await router.isReady();
  const wrapper = mount(ChangePasswordCard, {
    global: {
      components: elementPlusComponents,
      plugins: [
        [VueQueryPlugin, { queryClient: new QueryClient() }],
        pinia,
        router,
      ],
    },
  });
  return { router, wrapper };
}

describe("change-password card", () => {
  it("owns password validation and the refresh-before-return flow", async () => {
    server.use(
      http.post("/api/auth/change-password", () => new HttpResponse(null, { status: 204 })),
      http.post("/api/auth/refresh", () =>
        HttpResponse.json({ accessToken: "new-access", expiresIn: 1_800 }),
      ),
      http.get("/api/auth/session", () =>
        HttpResponse.json({
          user: { ...firstLoginUser, mustChangePassword: false },
          workspaces: [testWorkspace({ role: "viewer" })],
          truncated: false,
        }),
      ),
    );
    const { router, wrapper } = await mountCard();

    expect(wrapper.get(".brand-lockup strong").text()).toBe("Harness Evolution");
    expect(wrapper.get(".brand-lockup > div > span").text()).toBe("首次登录");

    await wrapper.get('input[name="oldPassword"]').setValue("temporary-password");
    await wrapper.get('input[name="newPassword"]').setValue("replacement-password");
    await wrapper.get('input[name="confirmPassword"]').setValue("different-password");
    await wrapper.get("form").trigger("submit");
    expect(wrapper.text()).toContain("两次输入的新密码不一致");

    await wrapper.get('input[name="confirmPassword"]').setValue("replacement-password");
    await wrapper.get("form").trigger("submit");
    await vi.waitFor(() =>
      expect(router.currentRoute.value.fullPath).toBe(`${ws}/sessions`),
    );
  });

  it("renders the configured brand name while keeping 首次登录 unchanged", async () => {
    const brand = {
      name: "Acme Diagnostics Self-Evolution Platform",
      subtitle: "Acme Self-Evolution",
    };
    const { wrapper } = await mountCard(brand);

    expect(wrapper.get(".brand-lockup strong").text()).toBe(brand.name);
    expect(wrapper.get(".brand-lockup > div > span").text()).toBe("首次登录");
    expect(wrapper.text()).toContain("设置新密码");
  });
});
